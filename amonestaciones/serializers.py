from rest_framework import serializers

from .models import Amonestacion, DocumentoLaboral


class DocumentoLaboralSerializer(serializers.ModelSerializer):
    tipo_display = serializers.CharField(source="get_tipo_display", read_only=True)

    class Meta:
        model = DocumentoLaboral
        fields = ("id", "tipo", "tipo_display", "nombre_original", "mime_type", "size", "activo", "creado_en")
        read_only_fields = fields


class AmonestacionSerializer(serializers.ModelSerializer):
    persona_nombre = serializers.CharField(source="persona.nombre_completo", read_only=True)
    persona_rut = serializers.CharField(source="persona.rut", read_only=True)
    instalacion_nombre = serializers.CharField(source="instalacion.nombre", read_only=True)

    class Meta:
        model = Amonestacion
        fields = (
            "id", "persona", "persona_nombre", "persona_rut", "instalacion", "instalacion_nombre",
            "fecha_hecho", "supervisor", "tipo_incumplimiento", "descripcion", "reincidencia",
            "antecedentes", "ciudad", "carta", "creado_en",
        )
        read_only_fields = ("id", "carta", "creado_en")

    def validate(self, attrs):
        required = ("persona", "instalacion", "fecha_hecho", "supervisor", "tipo_incumplimiento", "descripcion")
        for field in required:
            if not attrs.get(field):
                raise serializers.ValidationError({field: "Este campo es obligatorio."})
        return attrs

