"""Store merchandising and anonymous, first-party commercial analytics."""
import os
from collections import Counter
from datetime import timedelta

import json
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import URLError
from django.conf import settings
from django.core.cache import cache
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AnalyticsEvent, Promotion, StoreSession
from .permissions import IsVivadentAdmin
from .serializers import StoreSessionSerializer
from .views import PublicEventThrottle


class HeartbeatView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [PublicEventThrottle]

    def post(self, request):
        serializer = StoreSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        session_id = data.pop("session_id")
        data["cart_ids"] = list(dict.fromkeys(data["cart_ids"]))
        StoreSession.objects.update_or_create(session_id=session_id, defaults={**data, "last_seen": timezone.now()})
        return Response(status=204)


def payment_metrics(days):
    cached = cache.get(f"vivadent.payments.analytics.{days}")
    if cached is not None:
        return cached
    url = getattr(settings, "VIVADENT_PAYMENTS_ANALYTICS_URL", os.getenv("VIVADENT_PAYMENTS_ANALYTICS_URL", ""))
    key = getattr(settings, "VIVADENT_PAYMENTS_ANALYTICS_KEY", os.getenv("VIVADENT_PAYMENTS_ANALYTICS_KEY", ""))
    if not url or len(key) < 32:
        return {"available": False, "reason": "Configura la conexión privada con Vivadent Pagos para ver compras confirmadas."}
    try:
        request = Request(url + "?" + urlencode({"days": days}), headers={"X-Internal-Key": key, "Accept": "application/json"})
        with urlopen(request, timeout=3) as response:
            data = json.load(response)
        if not isinstance(data, dict) or not all(k in data for k in ("orders", "revenue", "products", "session_ids", "generated_at")):
            raise ValueError("Invalid payments response")
        data["available"] = True
        cache.set(f"vivadent.payments.analytics.{days}", data, 4)
        return data
    except (URLError, TimeoutError, OSError, ValueError):
        return {"available": False, "reason": "El sistema de pagos no respondió. Las ventas no se muestran como cero."}


class LiveAnalyticsView(APIView):
    permission_classes = [IsVivadentAdmin]

    def get(self, request):
        try:
            days = min(max(int(request.query_params.get("days", 7)), 1), 365)
        except ValueError:
            days = 7
        now = timezone.now()
        # Calendar days in Santiago, shared with the payment service.
        from zoneinfo import ZoneInfo
        zone = ZoneInfo("America/Santiago")
        today = now.astimezone(zone).date()
        from datetime import datetime, time
        start = datetime.combine(today - timedelta(days=days - 1), time.min, tzinfo=zone)
        events = AnalyticsEvent.objects.filter(created_at__gte=start, created_at__lte=now)
        active = StoreSession.objects.filter(active=True, last_seen__gte=now - timedelta(seconds=60))
        carts = active.exclude(cart_ids=[])
        cart_counts = Counter()
        # Deduplicate tabs of the same browser for live cart counts.
        seen = set()
        for session in carts.order_by("-last_seen"):
            if session.visitor_id not in seen:
                seen.add(session.visitor_id)
                cart_counts.update(set(session.cart_ids))
        all_promotions = dict(Promotion.objects.values_list("id", "title"))
        ranks = {}
        for kind, field in [("add_to_cart", "added"), ("remove_from_cart", "removed"), ("product_view", "views")]:
            for row in events.filter(event_type=kind, promotion_id__isnull=False).values("promotion_id").annotate(total=Count("id")):
                ranks.setdefault(row["promotion_id"], {"added": 0, "removed": 0, "views": 0, "purchased": 0})[field] = row["total"]
        payments = dict(payment_metrics(days))
        purchase_sessions = set(payments.pop("session_ids", []))
        for item in payments.get("products", []):
            pk = item["promotion_id"]
            ranks.setdefault(pk, {"added": 0, "removed": 0, "views": 0, "purchased": 0})["purchased"] = item["quantity"]
            all_promotions.setdefault(pk, item.get("title") or "Tratamiento retirado")
        visits = set(events.filter(event_type="page_view").values_list("session_id", flat=True))
        viewing = set(events.filter(event_type="product_view").values_list("session_id", flat=True)) & visits
        adding = set(events.filter(event_type="add_to_cart").values_list("session_id", flat=True)) & visits
        checkout = set(events.filter(event_type="checkout_started").values_list("session_id", flat=True)) & adding
        purchased = purchase_sessions & checkout
        products = [{"id": pk, "title": all_promotions.get(pk, "Tratamiento retirado"), **counts, "in_live_carts": cart_counts.get(pk, 0)} for pk, counts in ranks.items()]
        products.sort(key=lambda item: (-item["added"], -item["purchased"], item["id"]))
        series = list(events.filter(event_type="page_view").annotate(date=TruncDate("created_at", tzinfo=zone)).values("date").annotate(visits=Count("session_id", distinct=True)).order_by("date"))
        sources = list(events.filter(event_type="page_view").values("source").annotate(count=Count("session_id", distinct=True)).order_by("-count")[:10])
        devices = list(events.filter(event_type="page_view").values("device").annotate(count=Count("session_id", distinct=True)).order_by("-count"))
        activity = list(events.filter(event_type__in=["add_to_cart", "remove_from_cart", "checkout_started"]).order_by("-created_at").values("id", "event_type", "promotion_id", "created_at")[:15])
        for item in activity:
            item["title"] = all_promotions.get(item["promotion_id"], "Carrito de compra")
        response = Response({
            "generated_at": now, "period_days": days, "online_window_seconds": 60,
            "online": active.values("visitor_id").distinct().count(), "active_carts": len(seen),
            "live_products": [{"id": pk, "title": all_promotions.get(pk, "Tratamiento retirado"), "carts": count} for pk, count in cart_counts.most_common(20)],
            "visits": len(visits), "additions": events.filter(event_type="add_to_cart").count(),
            "removals": events.filter(event_type="remove_from_cart").count(),
            "checkout_sessions": events.filter(event_type="checkout_started").values("session_id").distinct().count(),
            "funnel": {"visits": len(visits), "product_views": len(viewing), "carts": len(adding), "checkouts": len(checkout), "purchases": len(purchased) if payments.get("available") else None},
            "conversion_rate": round(len(purchased) / len(visits) * 100, 1) if visits and payments.get("available") else None,
            "products": products[:50], "payments": payments, "series": series,
            "sources": sources, "devices": devices, "activity": activity,
        })
        response["Cache-Control"] = "no-store"
        return response
