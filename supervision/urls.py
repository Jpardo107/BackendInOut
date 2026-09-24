from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import SupervisionViewSet, SupervisionDetailViewSet, FotoSupervisionViewSet
from .rendiciones import RendicionGastoViewSet

router = DefaultRouter()
router.register(r'rendiciones-gastos', RendicionGastoViewSet, basename='rendiciones-gastos')
router.register(r'supervisiones', SupervisionViewSet, basename='supervisiones'),
router.register(r'detalle-supervisiones', SupervisionDetailViewSet, basename='detalle-supervisiones'),
router.register(r'fotos-supervision', FotoSupervisionViewSet, basename='foto-supervision')

urlpatterns = [
    path('', include(router.urls)),
]
