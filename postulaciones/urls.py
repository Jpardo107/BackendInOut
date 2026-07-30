from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AdminPostulacionViewSet,
    PreguntaAdminViewSet,
    PublicPostulacionViewSet,
    TipoInstalacionAdminViewSet,
    VacanteAdminViewSet,
)

router = DefaultRouter()
router.register("publicas/postulaciones", PublicPostulacionViewSet, basename="postulacion-publica")
router.register("admin/postulaciones", AdminPostulacionViewSet, basename="postulacion-admin")
router.register("admin/vacantes", VacanteAdminViewSet, basename="vacante-admin")
router.register("admin/preguntas", PreguntaAdminViewSet, basename="pregunta-admin")
router.register("admin/tipos-instalacion", TipoInstalacionAdminViewSet, basename="tipo-instalacion-admin")

urlpatterns = [path("", include(router.urls))]

