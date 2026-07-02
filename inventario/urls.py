from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import MovimientoInventarioViewSet, PrendaInventarioViewSet

router = DefaultRouter()
router.register(r"prendas", PrendaInventarioViewSet, basename="inventario-prendas")
router.register(r"movimientos", MovimientoInventarioViewSet, basename="inventario-movimientos")

urlpatterns = [
    path("", include(router.urls)),
]
