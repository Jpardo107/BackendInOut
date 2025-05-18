# documentacion/views.py
from rest_framework import viewsets, generics
from .models import DocumentoItem, EstadoDocumentacion
from .serializers import DocumentoItemSerializer, EstadoDocumentacionSerializer
from rest_framework.response import Response

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
