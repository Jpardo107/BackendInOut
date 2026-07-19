# instalacion/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import InstalacionViewSet, ZonaViewSet

router = DefaultRouter()
router.register(r'api/instalaciones', InstalacionViewSet, basename='instalacion')
router.register(r'api/zonas', ZonaViewSet, basename='zona')

urlpatterns = [
    path('', include(router.urls)),
]
