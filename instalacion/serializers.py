# instalacion/serializers.py

from rest_framework import serializers
from .models import Instalacion

class InstalacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Instalacion
        fields = '__all__'
