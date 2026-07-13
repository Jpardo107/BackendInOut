from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AutorizadosEntregaInventarioView,
    ComprobanteEntregaInventarioViewSet,
    ConfiguracionAlertaStockView,
    MovimientoInventarioViewSet,
    PrendaInventarioViewSet,
)

router = DefaultRouter()
router.register(r"prendas", PrendaInventarioViewSet, basename="inventario-prendas")
router.register(r"movimientos", MovimientoInventarioViewSet, basename="inventario-movimientos")
router.register(r"comprobantes-entrega", ComprobanteEntregaInventarioViewSet, basename="inventario-comprobantes-entrega")

urlpatterns = [
    path("autorizados-entrega/", AutorizadosEntregaInventarioView.as_view(), name="inventario-autorizados-entrega"),
    path("configuracion-alertas-stock/", ConfiguracionAlertaStockView.as_view(), name="inventario-configuracion-alertas-stock"),
    path("", include(router.urls)),
]
