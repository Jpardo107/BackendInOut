# supervision/serializers.py
from rest_framework import serializers
from .models import ConfiguracionResumenSolicitudes, Supervision, FotoSupervision
from .texto_solicitud import es_solicitud_real
from cargo_fijo.models import EstadoCargoFijo
from documentacion.models import EstadoDocumentacion


class FotoSupervisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FotoSupervision
        fields = ['id', 'url_imagen', 'descripcion', 'supervision']
        read_only_fields = ['id']


class SupervisionSerializer(serializers.ModelSerializer):
    fotos = FotoSupervisionSerializer(many=True, read_only=True)
    tiene_solicitud = serializers.SerializerMethodField()

    def get_tiene_solicitud(self, obj):
        return es_solicitud_real(obj.solicitudes)

    class Meta:
        model = Supervision
        fields = '__all__'

    extra_kwargs = {
        # Hacemos que los campos no sean obligatorios al realizar actualizaciones parciales (PATCH)
        'fecha': {'required': False},
        'hora_inicio': {'required': False},
        'hora_final': {'required': False},
        'instalacion': {'required': False},
        'supervisor': {'required': False},
        'novedades': {'required': False, 'allow_null': True},
        'solicitudes': {'required': False, 'allow_null': True},
        'latitud': {'required': False, 'allow_null': True},
        'longitud': {'required': False, 'allow_null': True},
    }

    # Validar el campo estado_solicitud
    def validate_estado_solicitud(self, value):
        # Valores permitidos al actualizar
        allowed_states = ['gestionado', 'entregado', 'denegado', 'pendiente']
        if self.instance and value not in allowed_states:
            raise serializers.ValidationError(
                f"Estado no permitido. Los valores permitidos son: {', '.join(allowed_states)}"
            )
        return value


class EstadoCargoFijoSerializer(serializers.ModelSerializer):
    cargo_fijo_nombre = serializers.CharField(source='cargo_fijo.nombre')

    class Meta:
        model = EstadoCargoFijo
        fields = ['cargo_fijo_nombre', 'cantidad_revisada', 'estado']
        ref_name = "EstadoCargoFijoDetalle"


class EstadoDocumentacionSerializer(serializers.ModelSerializer):
    documento_nombre = serializers.CharField(source='documento.nombre')

    class Meta:
        model = EstadoDocumentacion
        fields = ['documento_nombre', 'cantidad_revisada', 'validez']
        ref_name = "EstadoDocumentacionDetalle"


class SupervisionDetailSerializer(serializers.ModelSerializer):
    instalacion_nombre = serializers.CharField(source='instalacion.nombre')
    instalacion_direccion = serializers.CharField(source='instalacion.direccion')
    instalacion_comuna = serializers.CharField(source='instalacion.comuna')
    supervisor_nombre = serializers.SerializerMethodField()
    tiene_solicitud = serializers.SerializerMethodField()

    estado_cargos_fijos = EstadoCargoFijoSerializer(many=True, read_only=True)
    estado_documentos = EstadoDocumentacionSerializer(many=True, read_only=True)
    fotos = FotoSupervisionSerializer(many=True, read_only=True)

    class Meta:
        model = Supervision
        fields = [
            'id',
            'instalacion_nombre',
            'instalacion_direccion',
            'instalacion_comuna',
            'latitud',  # ✨ nuevo
            'longitud',  # ✨ nuevo
            'supervisor_nombre',
            'fecha',
            'hora_inicio',
            'hora_final',
            'novedades',
            'solicitudes',
            'tiene_solicitud',
            'estado_cargos_fijos',
            'estado_documentos',
            'fotos',
            'estado_solicitud',
            'detalles_revision',
        ]

    def get_supervisor_nombre(self, obj):
        return f"{obj.supervisor.nombres} {obj.supervisor.apellidos}" if obj.supervisor else None

    def get_tiene_solicitud(self, obj):
        return es_solicitud_real(obj.solicitudes)


class ConfiguracionResumenSolicitudesSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfiguracionResumenSolicitudes
        fields = ("activo", "destinatarios", "actualizado_en")
        read_only_fields = ("actualizado_en",)

    def validate_destinatarios(self, value):
        from .resumen_solicitudes import MAX_DESTINATARIOS

        if not isinstance(value, list):
            raise serializers.ValidationError("Debe ser una lista de correos.")
        field = serializers.EmailField()
        limpios = []
        for email in value:
            email = field.run_validation(str(email or "").strip().lower())
            if email not in limpios:
                limpios.append(email)
        if len(limpios) > MAX_DESTINATARIOS:
            raise serializers.ValidationError(f"Máximo {MAX_DESTINATARIOS} destinatarios.")
        return limpios
