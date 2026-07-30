from django.utils import timezone
from rest_framework import serializers

from documentacion.services.r2_storage import generate_signed_url
from user.services.rut import normalizar_rut
from .models import (
    AntecedenteAcademicoPostulante,
    CursoPostulante,
    DocumentoPostulacion,
    EntrevistaPostulacion,
    EvaluacionPostulacion,
    ExperienciaLaboralPostulante,
    HistorialPostulacion,
    ObservacionPostulacion,
    PostulacionGuardia,
    PreferenciaVacantePostulante,
    PreguntaAsignadaEvaluacion,
    PreguntaPostulacion,
    RespuestaPostulacion,
    TipoInstalacionLaboral,
    TokenQrPostulacion,
    VacanteGuardia,
)


def validar_rut_chileno(value):
    rut = normalizar_rut(value)
    if len(rut) < 8:
        raise serializers.ValidationError("RUT inválido.")
    cuerpo, dv = rut[:-1], rut[-1]
    suma, multiplicador = 0, 2
    for digito in reversed(cuerpo):
        suma += int(digito) * multiplicador
        multiplicador = 2 if multiplicador == 7 else multiplicador + 1
    esperado = 11 - (suma % 11)
    esperado = "0" if esperado == 11 else "K" if esperado == 10 else str(esperado)
    if dv != esperado:
        raise serializers.ValidationError("RUT inválido.")
    return rut


class TipoInstalacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoInstalacionLaboral
        fields = ("id", "nombre", "slug", "activo", "orden")


class EstudioSerializer(serializers.ModelSerializer):
    class Meta:
        model = AntecedenteAcademicoPostulante
        exclude = ("postulacion",)

    def validate(self, attrs):
        inicio, termino = attrs.get("anio_inicio"), attrs.get("anio_termino")
        if inicio and termino and termino < inicio:
            raise serializers.ValidationError({"anio_termino": "Debe ser posterior al año de inicio."})
        return attrs


class CursoSerializer(serializers.ModelSerializer):
    class Meta:
        model = CursoPostulante
        exclude = ("postulacion",)

    def validate(self, attrs):
        inicio, termino = attrs.get("fecha_realizacion"), attrs.get("fecha_vencimiento")
        if inicio and termino and termino < inicio:
            raise serializers.ValidationError({"fecha_vencimiento": "Debe ser posterior a la realización."})
        return attrs


class ExperienciaSerializer(serializers.ModelSerializer):
    tipo_instalacion_nombre = serializers.CharField(source="tipo_instalacion.nombre", read_only=True)

    class Meta:
        model = ExperienciaLaboralPostulante
        exclude = ("postulacion",)

    def validate(self, attrs):
        inicio, termino = attrs.get("fecha_inicio"), attrs.get("fecha_termino")
        if attrs.get("trabajo_actual"):
            attrs["fecha_termino"] = None
        elif termino and termino < inicio:
            raise serializers.ValidationError({"fecha_termino": "Debe ser posterior al inicio."})
        return attrs


class VacantePublicaSerializer(serializers.ModelSerializer):
    tipo_instalacion = serializers.CharField(source="tipo_instalacion.nombre")
    disponibles = serializers.IntegerField(read_only=True)
    horario = serializers.SerializerMethodField()

    class Meta:
        model = VacanteGuardia
        fields = (
            "public_id", "comuna_publica", "tipo_instalacion", "descripcion_publica",
            "jornada", "sistema_turno", "horario", "sueldo", "sueldo_liquido",
            "beneficios", "requisitos", "disponibles", "fecha_inicio",
            "requiere_os10_vigente", "requiere_licencia", "requiere_movilizacion",
        )

    def get_horario(self, obj):
        if not obj.hora_entrada or not obj.hora_salida:
            return ""
        return f"{obj.hora_entrada:%H:%M} a {obj.hora_salida:%H:%M}"


class PreferenciaSerializer(serializers.ModelSerializer):
    vacante = VacantePublicaSerializer(read_only=True)

    class Meta:
        model = PreferenciaVacantePostulante
        fields = ("id", "vacante", "orden_preferencia", "estado_interes", "seleccionada_en")


class PreguntaPublicaSerializer(serializers.ModelSerializer):
    respuesta = serializers.SerializerMethodField()

    class Meta:
        model = PreguntaAsignadaEvaluacion
        fields = ("id", "texto", "tipo_respuesta", "opciones", "obligatoria", "tipo_instalacion_nombre", "orden", "respuesta")

    def get_respuesta(self, obj):
        try:
            return obj.respuesta.respuesta
        except RespuestaPostulacion.DoesNotExist:
            return None


class DocumentoPublicoSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentoPostulacion
        fields = ("id", "tipo_documento", "nombre_original", "mime_type", "size", "estado", "fecha_vencimiento", "observaciones", "creado_en")
        read_only_fields = fields


class PostulacionPublicaSerializer(serializers.ModelSerializer):
    estudios = EstudioSerializer(many=True, read_only=True)
    cursos = CursoSerializer(many=True, read_only=True)
    experiencias = ExperienciaSerializer(many=True, read_only=True)
    preferencias = PreferenciaSerializer(many=True, read_only=True)
    documentos = DocumentoPublicoSerializer(many=True, read_only=True)
    nombre_completo = serializers.CharField(read_only=True)

    class Meta:
        model = PostulacionGuardia
        exclude = ("acceso_hash", "reclutador_asignado")
        read_only_fields = (
            "id", "id_publico", "codigo", "estado", "creado_en", "actualizado_en",
            "finalizada_en", "consentimiento_en",
        )

    def validate_rut(self, value):
        return validar_rut_chileno(value)

    def validate_presentacion(self, value):
        value = value.strip()
        if value and len(value) < 40:
            raise serializers.ValidationError("La presentación debe tener al menos 40 caracteres.")
        return value

    def validate_telefono(self, value):
        digits = "".join(char for char in value if char.isdigit())
        if len(digits) not in (9, 11):
            raise serializers.ValidationError("Ingresa un teléfono chileno válido.")
        return f"+56{digits[-9:]}"


class PreguntaAdminSerializer(serializers.ModelSerializer):
    tipo_instalacion_nombre = serializers.CharField(source="tipo_instalacion.nombre", read_only=True)

    class Meta:
        model = PreguntaPostulacion
        fields = "__all__"


class VacanteAdminSerializer(serializers.ModelSerializer):
    instalacion_nombre = serializers.CharField(source="instalacion.nombre", read_only=True)
    instalacion_direccion = serializers.CharField(source="instalacion.direccion", read_only=True)
    tipo_instalacion_nombre = serializers.CharField(source="tipo_instalacion.nombre", read_only=True)
    disponibles = serializers.IntegerField(read_only=True)

    class Meta:
        model = VacanteGuardia
        fields = "__all__"


class PreferenciaAdminSerializer(serializers.ModelSerializer):
    vacante = VacanteAdminSerializer(read_only=True)

    class Meta:
        model = PreferenciaVacantePostulante
        fields = ("id", "vacante", "orden_preferencia", "estado_interes", "seleccionada_en")


class DocumentoAdminSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = DocumentoPostulacion
        fields = "__all__"

    def get_url(self, obj):
        try:
            return generate_signed_url(obj.storage_key, expires=600, filename=obj.nombre_original, disposition="inline")
        except Exception:
            return ""


class EvaluacionAdminSerializer(serializers.ModelSerializer):
    preguntas = PreguntaPublicaSerializer(source="preguntas_asignadas", many=True, read_only=True)

    class Meta:
        model = EvaluacionPostulacion
        fields = ("id", "iniciada_en", "finalizada_en", "puntaje", "preguntas")


class PostulacionAdminListSerializer(serializers.ModelSerializer):
    nombre_completo = serializers.CharField(read_only=True)
    os10_vigente = serializers.SerializerMethodField()

    class Meta:
        model = PostulacionGuardia
        fields = ("id", "id_publico", "codigo", "nombre_completo", "rut", "email", "telefono", "comuna_residencia", "estado", "estado_os10", "os10_vigente", "creado_en", "finalizada_en")

    def get_os10_vigente(self, obj):
        return obj.estado_os10 == "vigente" and (not obj.os10_vencimiento or obj.os10_vencimiento >= timezone.localdate())


class PostulacionAdminDetalleSerializer(PostulacionPublicaSerializer):
    documentos = DocumentoAdminSerializer(many=True, read_only=True)
    preferencias = PreferenciaAdminSerializer(many=True, read_only=True)
    evaluacion = EvaluacionAdminSerializer(read_only=True)
    reclutador_nombre = serializers.SerializerMethodField()

    class Meta(PostulacionPublicaSerializer.Meta):
        exclude = ("acceso_hash",)

    def get_reclutador_nombre(self, obj):
        return str(obj.reclutador_asignado) if obj.reclutador_asignado else ""


class ObservacionSerializer(serializers.ModelSerializer):
    autor_nombre = serializers.CharField(source="autor.__str__", read_only=True)

    class Meta:
        model = ObservacionPostulacion
        fields = "__all__"
        read_only_fields = ("postulacion", "autor")


class EntrevistaSerializer(serializers.ModelSerializer):
    class Meta:
        model = EntrevistaPostulacion
        fields = "__all__"
        read_only_fields = ("postulacion",)
