# documentacion/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DocumentoItemViewSet, EstadoDocumentacionViewSet, EstadoDocumentacionCreateAPIView
from . import views

router = DefaultRouter()
router.register(r'documento-items', DocumentoItemViewSet)
router.register(r'estado-documentacion', EstadoDocumentacionViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('masivo/', EstadoDocumentacionCreateAPIView.as_view(), name='estado-documentacion-masivo'),
    path("instalaciones/<int:instalacion_id>/documentos/", views.documentos_por_instalacion),
    path("documentos/<int:documento_id>/access/", views.documento_access),
]
