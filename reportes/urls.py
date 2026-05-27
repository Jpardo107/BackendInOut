from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ReporteInformeViewSet

router = DefaultRouter()
router.register(r"reportes-informes", ReporteInformeViewSet, basename="reportes-informes")

urlpatterns = [
    path("", include(router.urls)),
]
