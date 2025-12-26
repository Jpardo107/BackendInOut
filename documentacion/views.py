# documentacion/views.py
from rest_framework import viewsets, generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from instalacion.models import Instalacion
from .models import DocumentoItem, EstadoDocumentacion, DocumentoInstalacion, documento_upload_key
from .serializers import DocumentoItemSerializer, EstadoDocumentacionSerializer, DocumentoInstalacionSerializer, \
    DocumentoInstalacionUploadSerializer
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from .services.r2_storage import upload_document, generate_signed_url


def user_can_access_instalacion(user, instalacion: Instalacion) -> bool:
    """
    Ajusta esta lógica a tu modelo real de permisos.
    Por ahora: solo usuarios autenticados.
    (Luego lo amarramos a empresa/instalación/rol como ya tienes en InOut).
    """
    return True

class DocumentoItemViewSet(viewsets.ModelViewSet):
    queryset = DocumentoItem.objects.all()
    serializer_class = DocumentoItemSerializer

class EstadoDocumentacionViewSet(viewsets.ModelViewSet):
    queryset = EstadoDocumentacion.objects.all()
    serializer_class = EstadoDocumentacionSerializer

# NUEVA vista para creación masiva
class EstadoDocumentacionCreateAPIView(generics.CreateAPIView):
    queryset = EstadoDocumentacion.objects.all()
    serializer_class = EstadoDocumentacionSerializer

    def create(self, request, *args, **kwargs):
        many = isinstance(request.data, list)
        serializer = self.get_serializer(data=request.data, many=many)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def documentos_por_instalacion(request, instalacion_id: int):
    instalacion = get_object_or_404(Instalacion, id=instalacion_id)

    if not user_can_access_instalacion(request.user, instalacion):
        return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

    if request.method == "GET":
        qs = DocumentoInstalacion.objects.filter(instalacion=instalacion)
        return Response(DocumentoInstalacionSerializer(qs, many=True).data)

    # POST upload
    serializer = DocumentoInstalacionUploadSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    file = serializer.validated_data["file"]
    titulo = serializer.validated_data["titulo"]
    categoria = serializer.validated_data.get("categoria", "")
    clasificacion = serializer.validated_data.get("clasificacion", "confidencial")

    key = documento_upload_key(instalacion.id, getattr(file, "name", ""))

    # Subir a R2
    upload_document(file=file, key=key)

    doc = DocumentoInstalacion.objects.create(
        instalacion=instalacion,
        titulo=titulo,
        categoria=categoria,
        clasificacion=clasificacion,
        storage_key=key,
        nombre_original=getattr(file, "name", "") or "",
        mime_type=getattr(file, "content_type", "") or "",
        size=getattr(file, "size", 0) or 0,
        creado_por=request.user,
    )

    return Response(
        {
            "id": doc.id,
            "message": "Documento subido correctamente",
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def documento_access(request, documento_id: int):
    doc = get_object_or_404(DocumentoInstalacion, id=documento_id)

    if not user_can_access_instalacion(request.user, doc.instalacion):
        return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

    # URL temporal (por defecto 60s). Puedes subirlo a 120s si quieres.
    url = generate_signed_url(doc.storage_key, expires=60)

    return Response({"url": url})