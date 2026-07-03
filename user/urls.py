from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import PersonalEmpresaViewSet, SupervisorListView

router = DefaultRouter()
router.register(r"personas", PersonalEmpresaViewSet, basename="personas")

urlpatterns = [
    path('supervisores/', SupervisorListView.as_view(), name='supervisores'),
    path('', include(router.urls)),
]
