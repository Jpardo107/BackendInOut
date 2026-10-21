from rest_framework import serializers
from .models import DocumentoItem, EstadoDocumentacion, DocumentoInstalacion, TipoDocumentoInstalacion


class TipoDocumentoInstalacionSerializer(serializers.ModelSerializer):
    documentos_subidos = serializers.IntegerField(read_only=True)

    class Meta:
        model = TipoDocumentoInstalacion
        fields = ("id", "codigo", "nombre", "orden", "documentos_subidos")
        read_only_fields = ("id", "codigo", "documentos_subidos")

    def validate_nombre(self, value):
        value = " ".join(value.split())
        if not value:
            raise serializers.ValidationError("Escribe el nombre del documento.")
        existing = TipoDocumentoInstalacion.objects.filter(nombre__iexact=value)
        if self.instance:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise serializers.ValidationError("Ya existe un documento con ese nombre.")
        return value


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
            "tipo_documento",
            "clasificacion",
            "estado_directiva",
            "nombre_original",
            "mime_type",
            "size",
            "created_at",
        )
        read_only_fields = fields


class DocumentoInstalacionUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    titulo = serializers.CharField(max_length=150)
    categoria = serializers.SlugRelatedField(slug_field="codigo", source="tipo_documento",
        queryset=TipoDocumentoInstalacion.objects.all())
    clasificacion = serializers.ChoiceField(
        choices=[("interno", "interno"), ("confidencial", "confidencial")],
        required=False,
        default="confidencial",
    )
    estado_directiva = serializers.ChoiceField(  # ✅ nuevo
        choices=["sin_tramitar", "tramitada", "aprobada"],
        required=False,
        default="sin_tramitar",
    )
