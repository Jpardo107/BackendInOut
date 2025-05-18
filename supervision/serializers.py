#supervision/serializers.py
from rest_framework import serializers
from .models import Supervision, FotoSupervision
from cargo_fijo.models import EstadoCargoFijo
from documentacion.models import EstadoDocumentacion


class FotoSupervisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FotoSupervision
        fields = ['id', 'url_imagen', 'descripcion', 'supervision']
        read_only_fields = ['id']


class SupervisionSerializer(serializers.ModelSerializer):
    fotos = FotoSupervisionSerializer(many=True, read_only=True)
    class Meta:
        model = Supervision
        fields = '__all__'


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
            'estado_cargos_fijos',
            'estado_documentos',
            'fotos'
        ]

    def get_supervisor_nombre(self, obj):
        return f"{obj.supervisor.nombres} {obj.supervisor.apellidos}" if obj.supervisor else None

