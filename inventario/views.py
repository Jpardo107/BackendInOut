from django.db import models
from rest_framework import filters, viewsets

from .models import MovimientoInventario, PrendaInventario
from .permissions import IsInventarioRole
from .serializers import MovimientoInventarioSerializer, PrendaInventarioSerializer


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
