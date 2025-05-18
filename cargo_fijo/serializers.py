from rest_framework import serializers

from supervision.models import Supervision
from .models import CargoFijoItem, EstadoCargoFijo

class CargoFijoItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = CargoFijoItem
        fields = '__all__'

class EstadoCargoFijoSerializer(serializers.ModelSerializer):
    cargo_fijo = serializers.PrimaryKeyRelatedField(queryset=CargoFijoItem.objects.all())
    supervision = serializers.PrimaryKeyRelatedField(queryset=Supervision.objects.all())

    class Meta:
        model = EstadoCargoFijo
        fields = ['cargo_fijo', 'supervision', 'cantidad_revisada', 'estado']
        ref_name = "EstadoCargoFijoDetalle"
