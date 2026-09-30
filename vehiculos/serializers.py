import re

from rest_framework import serializers
from .models import FotoVehiculo, MovimientoVehiculo, Vehiculo


class VehiculoSerializer(serializers.ModelSerializer):
    supervisor_nombre = serializers.SerializerMethodField()
    requiere_mantencion = serializers.SerializerMethodField()
    tiene_historial = serializers.SerializerMethodField()

    class Meta:
        model = Vehiculo
        fields = ["id", "patente", "marca", "modelo", "anio", "kilometraje_actual",
                  "kilometraje_mantencion", "activo", "supervisor_actual", "supervisor_nombre",
                  "requiere_mantencion", "tiene_historial", "version"]
        read_only_fields = ["supervisor_actual", "version"]
        extra_kwargs = {
            "kilometraje_actual": {"min_value": 0, "max_value": 2147483647},
            "kilometraje_mantencion": {"min_value": 1, "max_value": 2147483647},
            "anio": {"min_value": 1900, "max_value": 2200},
        }

    def validate_patente(self, value):
        value = re.sub(r"[\s-]", "", value).upper()
        if not re.fullmatch(r"[A-Z0-9]{4,12}", value):
            raise serializers.ValidationError("Ingresa una patente válida de 4 a 12 letras o números.")
        qs = Vehiculo.objects.filter(patente=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Esta patente ya está registrada.")
        return value

    def validate(self, attrs):
        if self.instance:
            if self.instance.supervisor_actual_id and attrs.get("activo") is False:
                raise serializers.ValidationError("No se puede desactivar un vehículo pendiente de entrega.")
            if ("kilometraje_actual" in attrs and attrs["kilometraje_actual"] != self.instance.kilometraje_actual
                    and self.instance.movimientos.exists()):
                raise serializers.ValidationError("El kilometraje se actualiza mediante recepciones y entregas.")
        return attrs

    def get_supervisor_nombre(self, obj):
        return str(obj.supervisor_actual) if obj.supervisor_actual_id else None

    def get_requiere_mantencion(self, obj):
        return obj.kilometraje_mantencion is not None and obj.kilometraje_actual >= obj.kilometraje_mantencion

    def get_tiene_historial(self, obj):
        return obj.movimientos.exists()


class FotoEntradaSerializer(serializers.Serializer):
    vista = serializers.ChoiceField(choices=FotoVehiculo.VISTAS)
    tiene_novedad = serializers.BooleanField(required=True)
    novedad = serializers.CharField(max_length=3000, allow_blank=True, default="")

    def validate(self, attrs):
        if attrs["tiene_novedad"] and not attrs["novedad"].strip():
            raise serializers.ValidationError("Describe la novedad de la fotografía.")
        if not attrs["tiene_novedad"]:
            attrs["novedad"] = ""
        return attrs


class MovimientoEntradaSerializer(serializers.Serializer):
    solicitud_id = serializers.UUIDField()
    version = serializers.IntegerField(min_value=0)
    tipo = serializers.ChoiceField(choices=MovimientoVehiculo.TIPOS)
    kilometraje = serializers.IntegerField(min_value=0, max_value=2147483647)
    gata = serializers.BooleanField(required=True)
    llave_cruz = serializers.BooleanField(required=True)
    extintor = serializers.BooleanField(required=True)
    triangulo = serializers.BooleanField(required=True)
    resumen = serializers.CharField(max_length=5000, allow_blank=True, default="")
    fotos = FotoEntradaSerializer(many=True, min_length=5, max_length=20)

    def validate_fotos(self, fotos):
        vistas = [foto["vista"] for foto in fotos if foto["vista"] != "extra"]
        if sorted(vistas) != sorted(["frontal", "trasera", "izquierdo", "derecho", "tablero"]):
            raise serializers.ValidationError("Incluye una foto frontal, trasera, izquierda, derecha y del tablero.")
        return fotos


class MovimientoSerializer(serializers.ModelSerializer):
    fotos = serializers.SerializerMethodField()

    class Meta:
        model = MovimientoVehiculo
        fields = ["id", "solicitud_id", "vehiculo", "supervisor", "supervisor_nombre", "tipo",
                  "kilometraje", "gata", "llave_cruz", "extintor", "triangulo", "resumen",
                  "creado_en", "recepcion", "fotos"]

    def get_fotos(self, obj):
        return [{"id": foto.id, "vista": foto.vista, "tiene_novedad": foto.tiene_novedad,
                 "novedad": foto.novedad} for foto in obj.fotos.all()]
