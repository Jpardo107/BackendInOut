from rest_framework import serializers
from .models import Actividad, DiaEspecial, Pauta, TIPOS


class HorariosMixin:
    def validate(self, attrs):
        attrs = super().validate(attrs)
        for key in ("hora_inicio", "hora_fin"):
            value = attrs.get(key, getattr(self.instance, key, None))
            if value and (value.minute not in (0, 30) or value.second or value.microsecond):
                raise serializers.ValidationError({key: "Selecciona minutos 00 o 30."})
        start = attrs.get("hora_inicio", getattr(self.instance, "hora_inicio", None))
        end = attrs.get("hora_fin", getattr(self.instance, "hora_fin", None))
        if start and end and start == end:
            raise serializers.ValidationError({"hora_fin": "El término debe ser distinto del inicio. Para un turno nocturno selecciona la hora del día siguiente."})
        return attrs


class PautaSerializer(HorariosMixin, serializers.ModelSerializer):
    class Meta:
        model = Pauta
        exclude = ["usuario"]


class DiaSerializer(HorariosMixin, serializers.ModelSerializer):
    class Meta:
        model = DiaEspecial
        exclude = ["usuario"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance and attrs.get("fecha", self.instance.fecha) != self.instance.fecha:
            raise serializers.ValidationError({"fecha": "Crea un ajuste para la nueva fecha y restaura el anterior si corresponde."})
        if attrs.get("tipo", getattr(self.instance, "tipo", None)) != "libre":
            for field in ("hora_inicio", "hora_fin"):
                if not attrs.get(field, getattr(self.instance, field, None)):
                    raise serializers.ValidationError({field: "Selecciona el horario del turno."})
        return attrs


class ActividadSerializer(HorariosMixin, serializers.ModelSerializer):
    class Meta:
        model = Actividad
        exclude = ["usuario"]
        read_only_fields = ["creada_en", "actualizada_en"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        ref = attrs.get("registro_vinculado", getattr(self.instance, "registro_vinculado", ""))
        if ref:
            from .services import registro_pertenece
            if not registro_pertenece(self.context["request"].user, ref):
                raise serializers.ValidationError({"registro_vinculado": "El registro no existe o no te pertenece."})
            if attrs.get("estado", getattr(self.instance, "estado", "pendiente")) != "realizada":
                raise serializers.ValidationError({"estado": "Una actividad vinculada debe estar realizada."})
        return attrs


class FiltroSerializer(serializers.Serializer):
    desde = serializers.DateField()
    hasta = serializers.DateField()
    zona = serializers.CharField(default="America/Santiago")
    hora_desde = serializers.TimeField(required=False)
    hora_hasta = serializers.TimeField(required=False)
    tipo = serializers.ChoiceField(choices=[("", "Todos"), *TIPOS, ("extra", "Turno extra")], required=False, allow_blank=True)

    def validate(self, attrs):
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        if attrs["hasta"].year > 9998:
            raise serializers.ValidationError("La fecha está fuera del rango permitido.")
        if attrs["hasta"] < attrs["desde"] or (attrs["hasta"] - attrs["desde"]).days > 365:
            raise serializers.ValidationError("Selecciona un rango ordenado de hasta 366 días.")
        if bool(attrs.get("hora_desde")) != bool(attrs.get("hora_hasta")):
            raise serializers.ValidationError("Indica ambas horas del filtro.")
        for field in ("hora_desde", "hora_hasta"):
            value = attrs.get(field)
            if value and (value.minute not in (0, 30) or value.second or value.microsecond):
                raise serializers.ValidationError("Los filtros de hora usan minutos 00 o 30.")
        try:
            ZoneInfo(attrs["zona"])
        except (ZoneInfoNotFoundError, ValueError):
            raise serializers.ValidationError({"zona": "Zona horaria no válida."})
        return attrs
