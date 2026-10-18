from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import PersonalEmpresaViewSet, SupervisorListView

from .rondas_integration import GuardiaRondasLookupView

router = DefaultRouter()
router.register(r"personas", PersonalEmpresaViewSet, basename="personas")

urlpatterns = [
    path("integraciones/rondas/guardia/", GuardiaRondasLookupView.as_view(), name="rondas-guardia"),
    path('supervisores/', SupervisorListView.as_view(), name='supervisores'),
    path('', include(router.urls)),
]
