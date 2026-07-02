from django.db import models
from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from .models import MovimientoInventario, PrendaInventario
from .permissions import IsInventarioRole
from .serializers import MovimientoInventarioSerializer, PrendaInventarioSerializer


def normalize_scanned_code(value):
    code = str(value or "").strip()
    if not code:
        return ""
    return code.rstrip("/").split("/")[-1] if "/" in code else code


class PrendaInventarioViewSet(viewsets.ModelViewSet):
    serializer_class = PrendaInventarioSerializer
    permission_classes = [IsInventarioRole]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        "nombre_prenda",
        "talla_prenda",
        "codigo_barra",
        "codigo_qr",
    ]
    ordering_fields = [
        "nombre_prenda",
        "talla_prenda",
        "stock_actual",
        "stock_critico",
        "actualizado_en",
    ]
    ordering = ["nombre_normalizado", "talla_normalizada"]

    def get_queryset(self):
        queryset = PrendaInventario.objects.all()
        activo = self.request.query_params.get("activo")
        bajo_stock = self.request.query_params.get("bajo_stock")

        if activo is not None:
            queryset = queryset.filter(activo=activo.lower() in ("1", "true", "si", "yes"))

        if bajo_stock is not None and bajo_stock.lower() in ("1", "true", "si", "yes"):
            queryset = queryset.filter(stock_actual__lte=models.F("stock_critico"))

        return queryset

    @action(detail=False, methods=["get"], url_path="buscar-codigo")
    def buscar_codigo(self, request):
        codigo = request.query_params.get("codigo", "")
        codigo_normalizado = normalize_scanned_code(codigo)

        if not codigo_normalizado:
            raise ValidationError({"codigo": "Debes indicar un codigo para buscar."})

        prenda = (
            self.get_queryset()
            .filter(
                models.Q(codigo_barra__iexact=codigo)
                | models.Q(codigo_qr__iexact=codigo)
                | models.Q(codigo_barra__iexact=codigo_normalizado)
                | models.Q(codigo_qr__iendswith=f"/{codigo_normalizado}")
            )
            .first()
        )

        if not prenda:
            raise NotFound("No existe una prenda asociada al codigo escaneado.")

        return Response(self.get_serializer(prenda).data)


class MovimientoInventarioViewSet(viewsets.ModelViewSet):
    serializer_class = MovimientoInventarioSerializer
    permission_classes = [IsInventarioRole]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        "prenda__nombre_prenda",
        "prenda__talla_prenda",
        "prenda__codigo_barra",
        "observacion",
    ]
    ordering_fields = ["creado_en", "tipo", "cantidad"]
    ordering = ["-creado_en", "-id"]

    def get_queryset(self):
        queryset = (
            MovimientoInventario.objects
            .select_related("prenda", "usuario_registro", "usuario_final")
        )
        tipo = self.request.query_params.get("tipo")
        prenda_id = self.request.query_params.get("prenda")

        if tipo:
            queryset = queryset.filter(tipo=tipo)

        if prenda_id:
            queryset = queryset.filter(prenda_id=prenda_id)

        return queryset
