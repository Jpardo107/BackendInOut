from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import ActividadViewSet, DiaViewSet, PautaViewSet, opciones, panel

router = DefaultRouter()
router.register("actividades", ActividadViewSet)
router.register("dias", DiaViewSet)
router.register("pautas", PautaViewSet)
urlpatterns = [path("panel/", panel), path("opciones/", opciones), path("", include(router.urls))]
