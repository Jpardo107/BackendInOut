# cargo_fijo/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CargoFijoItemViewSet, EstadoCargoFijoViewSet, EstadoCargoFijoCreateAPIView

router = DefaultRouter()
router.register(r'cargo-fijo-items', CargoFijoItemViewSet)
router.register(r'estado-cargo-fijo', EstadoCargoFijoViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('masivo/', EstadoCargoFijoCreateAPIView.as_view(), name='estado-cargo-fijo-masivo'),
]
