from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AmonestacionViewSet, DocumentoLaboralViewSet


router = DefaultRouter()
router.register("documentos-laborales", DocumentoLaboralViewSet, basename="documentos-laborales")
router.register("amonestaciones", AmonestacionViewSet, basename="amonestaciones")

urlpatterns = [path("", include(router.urls))]

