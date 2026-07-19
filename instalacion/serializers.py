# instalacion/serializers.py

from django.db import transaction
from rest_framework import serializers
from .models import Instalacion, Zona


class ZonaSerializer(serializers.ModelSerializer):
    instalaciones_asignadas = serializers.SerializerMethodField()

    class Meta:
        model = Zona
        fields = ("id", "codigo", "nombre", "instalaciones_asignadas", "creado_en", "actualizado_en")
        read_only_fields = ("id", "instalaciones_asignadas", "creado_en", "actualizado_en")

    def get_instalaciones_asignadas(self, obj):
        return Instalacion.objects.filter(zona=obj.codigo).count()

    def update(self, instance, validated_data):
        codigo_anterior = instance.codigo
        with transaction.atomic():
            instance = super().update(instance, validated_data)
            if codigo_anterior != instance.codigo:
                Instalacion.objects.filter(zona=codigo_anterior).update(zona=instance.codigo)
        return instance

class InstalacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Instalacion
        fields = '__all__'

    def validate_zona(self, value):
        codigo = str(value or "").strip().lower()
        if not Zona.objects.filter(codigo=codigo).exists():
            raise serializers.ValidationError("La zona seleccionada no existe.")
        return codigo
