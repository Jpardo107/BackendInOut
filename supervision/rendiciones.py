"""Registro de gastos y consulta de comprobantes privados en R2."""
import logging
from datetime import datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.db import transaction
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from backend_inout.live_events import can_access_live
from documentacion.services.r2_storage import delete_document, generate_signed_url, upload_document
from .models import RendicionGasto

logger = logging.getLogger(__name__)
CHILE = ZoneInfo("America/Santiago")


class RendicionSerializer(serializers.ModelSerializer):
    imagen = serializers.ImageField(write_only=True)

    class Meta:
        model = RendicionGasto
        fields = ["id", "supervisor", "supervisor_nombre", "instalacion", "persona", "creada_en", "imagen"]
        read_only_fields = ["id", "supervisor", "supervisor_nombre", "creada_en"]

    def validate_imagen(self, image):
        if image.size > 10 * 1024 * 1024:
            raise ValidationError("La imagen no puede superar los 10 MB.")
        if image.image.format not in {"JPEG", "PNG", "WEBP"}:
            raise ValidationError("Usa una imagen JPG, PNG o WebP.")
        return image


class RendicionFilters(serializers.Serializer):
    supervisor = serializers.IntegerField(min_value=1, required=False)
    instalacion = serializers.CharField(max_length=220, required=False)
    persona = serializers.CharField(max_length=220, required=False)
    fecha_desde = serializers.DateField(required=False)
    fecha_hasta = serializers.DateField(required=False)

    def validate(self, data):
        if data.get("fecha_desde") and data.get("fecha_hasta") and data["fecha_desde"] > data["fecha_hasta"]:
            raise ValidationError("La fecha desde no puede ser posterior a la fecha hasta.")
        return data


class RendicionPagination(PageNumberPagination):
    page_size = 20


class RendicionGastoViewSet(mixins.CreateModelMixin, mixins.ListModelMixin,
                           mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = RendicionSerializer
    pagination_class = RendicionPagination

    def scoped_queryset(self):
        queryset = RendicionGasto.objects.all()
        if not can_access_live(self.request.user):
            queryset = queryset.filter(supervisor=self.request.user)
        return queryset

    def get_queryset(self):
        queryset = self.scoped_queryset()
        if self.action != "list":
            return queryset
        filters = RendicionFilters(data=self.request.query_params)
        filters.is_valid(raise_exception=True)
        data = filters.validated_data
        for field in ("instalacion", "persona"):
            if data.get(field):
                queryset = queryset.filter(**{f"{field}__icontains": data[field]})
        if data.get("supervisor"):
            queryset = queryset.filter(supervisor_id=data["supervisor"])
        if data.get("fecha_desde"):
            start = datetime.combine(data["fecha_desde"], time.min, tzinfo=CHILE)
            queryset = queryset.filter(creada_en__gte=start)
        if data.get("fecha_hasta"):
            end = datetime.combine(data["fecha_hasta"] + timedelta(days=1), time.min, tzinfo=CHILE)
            queryset = queryset.filter(creada_en__lt=end)
        return queryset

    def perform_create(self, serializer):
        image = serializer.validated_data.pop("imagen")
        extension = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}[image.image.format]
        key = f"rendiciones-gastos/{uuid4().hex}.{extension}"
        try:
            upload_document(image, key)
        except Exception as exc:
            logger.exception("No se pudo subir el comprobante de gasto")
            raise APIException("No se pudo guardar la imagen. Intenta nuevamente.") from exc
        try:
            with transaction.atomic():
                serializer.save(
                    supervisor=self.request.user,
                    supervisor_nombre=str(self.request.user).strip(),
                    storage_key=key,
                )
        except Exception:
            try:
                delete_document(key)
            except Exception:
                logger.exception("No se pudo limpiar el comprobante %s", key)
            raise

    @action(detail=False, methods=["get"])
    def filtros(self, request):
        supervisors = self.scoped_queryset().order_by("supervisor_nombre").values(
            "supervisor", "supervisor_nombre"
        ).distinct()
        return Response({"supervisores": list(supervisors)})

    @action(detail=True, methods=["get"])
    def imagen(self, request, pk=None):
        expense = self.get_object()
        try:
            url = generate_signed_url(expense.storage_key, expires=3600, disposition="inline",
                                      filename=f"rendicion-{expense.id}.{expense.storage_key.rsplit('.', 1)[-1]}")
        except Exception as exc:
            logger.exception("No se pudo abrir el comprobante %s", expense.id)
            raise APIException("No se pudo abrir la imagen. Intenta nuevamente.") from exc
        return Response({"url": url})
