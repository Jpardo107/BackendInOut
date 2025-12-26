from rest_framework import serializers
from .models import DocumentoItem, EstadoDocumentacion, DocumentoInstalacion


class DocumentoItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentoItem
        fields = '__all__'

class EstadoDocumentacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = EstadoDocumentacion
        fields = '__all__'
        ref_name = "EstadoDocumentacionOriginal"

class DocumentoInstalacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentoInstalacion
        fields = (
            "id",
            "instalacion",
            "titulo",
            "categoria",
            "clasificacion",
            "nombre_original",
            "mime_type",
            "size",
            "created_at",
        )
        read_only_fields = fields


class DocumentoInstalacionUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    titulo = serializers.CharField(max_length=150)
    categoria = serializers.CharField(max_length=80, required=False, allow_blank=True)
    clasificacion = serializers.ChoiceField(
        choices=[("interno", "interno"), ("confidencial", "confidencial")],
        required=False,
        default="confidencial",
    )