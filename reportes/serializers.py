from django.utils import timezone
from rest_framework import serializers

from documentacion.services.r2_storage import generate_signed_url
from instalacion.models import Instalacion

from .models import ImagenReporteInforme, ReporteInforme


TIPO_REPORTE_ALIASES = {
    "pre-informe": ReporteInforme.TIPO_PRE_INFORME,
    "pre_informe": ReporteInforme.TIPO_PRE_INFORME,
    "reporte-vulnerabilidades": ReporteInforme.TIPO_VULNERABILIDADES,
    "vulnerabilidades": ReporteInforme.TIPO_VULNERABILIDADES,
}


class ImagenReporteInformeSerializer(serializers.ModelSerializer):
    url_imagen = serializers.SerializerMethodField()

    class Meta:
        model = ImagenReporteInforme
        fields = (
            "id",
            "url_imagen",
            "storage_key",
            "nombre_original",
            "mime_type",
            "size",
            "descripcion",
            "recomendacion_usuario",
            "orden",
            "creado_en",
        )
        read_only_fields = fields

    def get_url_imagen(self, obj):
        if not obj.storage_key:
            return ""
        return generate_signed_url(obj.storage_key, expires=300, disposition="inline")


class ReporteInformeListSerializer(serializers.ModelSerializer):
    instalacion_nombre = serializers.CharField(source="instalacion.nombre", read_only=True)
    usuario_creador_nombre = serializers.SerializerMethodField()
    cantidad_imagenes = serializers.IntegerField(read_only=True)

    class Meta:
        model = ReporteInforme
        fields = (
            "id",
            "tipo_reporte",
            "instalacion",
            "instalacion_nombre",
            "zona",
            "usuario_creador",
            "usuario_creador_nombre",
            "autor_nombre",
            "autor_cargo",
            "criticidad_general",
            "estado",
            "fecha_emision",
            "creado_en",
            "actualizado_en",
            "cantidad_imagenes",
        )
        read_only_fields = fields

    def get_usuario_creador_nombre(self, obj):
        return str(obj.usuario_creador)


class ReporteInformeDetailSerializer(serializers.ModelSerializer):
    instalacion_nombre = serializers.CharField(source="instalacion.nombre", read_only=True)
    usuario_creador_nombre = serializers.SerializerMethodField()
    imagenes = ImagenReporteInformeSerializer(many=True, read_only=True)

    class Meta:
        model = ReporteInforme
        fields = (
            "id",
            "tipo_reporte",
            "instalacion",
            "instalacion_nombre",
            "zona",
            "usuario_creador",
            "usuario_creador_nombre",
            "autor_nombre",
            "autor_cargo",
            "descripcion_hechos",
            "analisis_previo",
            "analisis_final_usuario",
            "personal_presente",
            "personal_policial_presente",
            "carabinero_cargo",
            "patente_patrulla",
            "numero_carro_policial",
            "criticidad_general",
            "resumen_ejecutivo",
            "conclusion_profesional",
            "riesgos_detectados",
            "recomendaciones_ia",
            "matriz_riesgo",
            "texto_final_pdf",
            "respuesta_ia_raw",
            "archivo_origen_storage_key",
            "archivo_origen_nombre",
            "archivo_origen_mime_type",
            "archivo_origen_size",
            "texto_extraido_origen",
            "estado",
            "fecha_emision",
            "creado_en",
            "actualizado_en",
            "imagenes",
        )
        read_only_fields = fields

    def get_usuario_creador_nombre(self, obj):
        return str(obj.usuario_creador)


class ReporteInformeCreateSerializer(serializers.ModelSerializer):
    instalacion = serializers.PrimaryKeyRelatedField(queryset=Instalacion.objects.all())
    tipo_reporte = serializers.CharField()
    fecha_emision = serializers.DateField(required=False)
    autor_nombre = serializers.CharField(max_length=255, required=False, allow_blank=True)
    autor_cargo = serializers.CharField(max_length=150, required=False, allow_blank=True)

    class Meta:
        model = ReporteInforme
        fields = (
            "tipo_reporte",
            "instalacion",
            "zona",
            "autor_nombre",
            "autor_cargo",
            "descripcion_hechos",
            "analisis_previo",
            "analisis_final_usuario",
            "personal_presente",
            "personal_policial_presente",
            "carabinero_cargo",
            "patente_patrulla",
            "numero_carro_policial",
            "fecha_emision",
        )

    def validate_tipo_reporte(self, value):
        normalized = TIPO_REPORTE_ALIASES.get(str(value).strip())
        if not normalized:
            raise serializers.ValidationError(
                "Tipo de reporte invalido. Usa pre-informe o reporte-vulnerabilidades."
            )
        return normalized

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)

        if "fecha_emision" not in attrs:
            attrs["fecha_emision"] = timezone.localdate()

        if not attrs.get("autor_nombre") and user and user.is_authenticated:
            attrs["autor_nombre"] = f"{user.nombres} {user.apellidos}".strip()

        if not attrs.get("autor_cargo") and user and user.is_authenticated:
            attrs["autor_cargo"] = user.cargo.nombre if getattr(user, "cargo", None) else ""

        if not attrs.get("zona") and attrs.get("instalacion"):
            attrs["zona"] = attrs["instalacion"].zona

        tipo_reporte = attrs.get("tipo_reporte")
        descripcion_hechos = attrs.get("descripcion_hechos", "")
        if tipo_reporte == ReporteInforme.TIPO_VULNERABILIDADES and not attrs.get("analisis_previo"):
            attrs["analisis_previo"] = descripcion_hechos

        return attrs


class ReporteIAResultSerializer(serializers.ModelSerializer):
    imagenes = ImagenReporteInformeSerializer(many=True, read_only=True)

    class Meta:
        model = ReporteInforme
        fields = (
            "id",
            "estado",
            "criticidad_general",
            "resumen_ejecutivo",
            "conclusion_profesional",
            "riesgos_detectados",
            "recomendaciones_ia",
            "matriz_riesgo",
            "texto_final_pdf",
            "respuesta_ia_raw",
            "imagenes",
            "actualizado_en",
        )
        read_only_fields = fields
