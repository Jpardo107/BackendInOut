from rest_framework import serializers
from .models import DocumentoItem, EstadoDocumentacion


class DocumentoItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentoItem
        fields = '__all__'

class EstadoDocumentacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = EstadoDocumentacion
        fields = '__all__'
        ref_name = "EstadoDocumentacionOriginal"