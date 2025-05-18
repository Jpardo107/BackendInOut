# instalacion/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import InstalacionViewSet

router = DefaultRouter()
router.register(r'api/instalaciones', InstalacionViewSet, basename='instalacion')

urlpatterns = [
    path('', include(router.urls)),
]
