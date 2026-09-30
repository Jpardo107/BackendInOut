from rest_framework.routers import DefaultRouter
from .views import VehiculoViewSet

router = DefaultRouter()
router.register("", VehiculoViewSet, basename="vehiculo")
urlpatterns = router.urls
