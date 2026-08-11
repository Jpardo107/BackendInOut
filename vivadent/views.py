from datetime import timedelta

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import AnalyticsEvent, Promotion, SiteImage, SiteText
from .permissions import IsVivadentAdmin
from .serializers import AnalyticsEventSerializer, PromotionSerializer, SiteImageSerializer, SiteTextSerializer, VivadentTokenSerializer
from .services.storage import save_uploaded_image


class PublicEventThrottle(AnonRateThrottle):
    rate = "120/min"


class VivadentTokenView(TokenObtainPairView):
    permission_classes = [permissions.AllowAny]
    serializer_class = VivadentTokenSerializer


class PromotionViewSet(viewsets.ModelViewSet):
    queryset = Promotion.objects.all()
    serializer_class = PromotionSerializer
    permission_classes = [IsVivadentAdmin]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser])
    def upload(self, request, pk=None):
        item = self.get_object()
        image = request.FILES.get("image")
        if not image or not (image.content_type or "").startswith("image/") or image.size > 8 * 1024 * 1024:
            return Response({"image": "Debes adjuntar una imagen válida de hasta 8 MB."}, status=status.HTTP_400_BAD_REQUEST)
        item.image_url = save_uploaded_image(image)
        item.save(update_fields=["image_url", "updated_at"])
        return Response(self.get_serializer(item).data)


class SiteImageViewSet(viewsets.ModelViewSet):
    queryset = SiteImage.objects.all()
    serializer_class = SiteImageSerializer
    permission_classes = [IsVivadentAdmin]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser])
    def upload(self, request, pk=None):
        item = self.get_object()
        image = request.FILES.get("image")
        if not image or not (image.content_type or "").startswith("image/"):
            return Response({"image": "Debes adjuntar una imagen válida."}, status=status.HTTP_400_BAD_REQUEST)
        if image.size > 8 * 1024 * 1024:
            return Response({"image": "La imagen no puede superar 8 MB."}, status=status.HTTP_400_BAD_REQUEST)
        item.image_url = save_uploaded_image(image)
        item.save(update_fields=["image_url", "updated_at"])
        return Response(self.get_serializer(item).data)


class SiteTextViewSet(viewsets.ModelViewSet):
    queryset = SiteText.objects.all()
    serializer_class = SiteTextSerializer
    permission_classes = [IsVivadentAdmin]


class PublicContentView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        promotions = Promotion.objects.filter(status="active")
        return Response({
            "promotions": PromotionSerializer(promotions, many=True).data,
            "images": SiteImageSerializer(SiteImage.objects.all(), many=True).data,
            "texts": SiteTextSerializer(SiteText.objects.all(), many=True).data,
        })


class TrackEventView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [PublicEventThrottle]

    def post(self, request):
        serializer = AnalyticsEventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=status.HTTP_201_CREATED)


class AnalyticsDashboardView(APIView):
    permission_classes = [IsVivadentAdmin]

    def get(self, request):
        try:
            days = min(max(int(request.query_params.get("days", 30)), 1), 365)
        except ValueError:
            days = 30
        start = timezone.now() - timedelta(days=days)
        events = AnalyticsEvent.objects.filter(created_at__gte=start)
        sessions = events.values("session_id").distinct().count()
        contacts = events.filter(event_type="click", target__in=["whatsapp", "phone", "email"]).count()
        external_clicks = events.filter(event_type="click").count()
        series = events.filter(event_type="page_view").annotate(day=TruncDate("created_at")).values("day").annotate(value=Count("session_id", distinct=True)).order_by("day")
        section_views = events.filter(event_type="section_view").values("section").annotate(views=Count("id"), sessions=Count("session_id", distinct=True)).order_by("-views")
        section_clicks = {row["section"]: row["clicks"] for row in events.filter(event_type="click").values("section").annotate(clicks=Count("id"))}
        sections = []
        for row in section_views:
            clicks = section_clicks.get(row["section"], 0)
            sections.append({**row, "clicks": clicks, "conversion_rate": round(clicks / row["sessions"] * 100, 1) if row["sessions"] else 0})
        channels = events.filter(event_type="click").exclude(target="").values("target").annotate(clicks=Count("id")).order_by("-clicks")
        sources = events.exclude(source="").values("source").annotate(count=Count("session_id", distinct=True)).order_by("-count")
        devices = events.exclude(device="").values("device").annotate(count=Count("session_id", distinct=True)).order_by("-count")
        return Response({
            "period_days": days,
            "visits": sessions,
            "contacts": contacts,
            "conversion_rate": round((contacts / sessions * 100), 1) if sessions else 0,
            "external_clicks": external_clicks,
            "series": [{"date": row["day"], "value": row["value"]} for row in series],
            "sections": sections, "channels": list(channels), "sources": list(sources), "devices": list(devices),
        })


@api_view(["GET"])
@permission_classes([IsVivadentAdmin])
def current_user(request):
    return Response({"id": request.user.id, "username": request.user.username, "name": f"{request.user.nombres} {request.user.apellidos}".strip(), "email": request.user.email})
