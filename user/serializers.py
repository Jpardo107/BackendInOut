from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework import serializers
from .models import Usuario


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):

    def validate(self, attrs):
        data = super().validate(attrs)

        # Agregamos datos extra del usuario
        data['user'] = {
            'id': self.user.id,
            'username': self.user.username,
            'nombres': self.user.nombres,
            'apellidos': self.user.apellidos,
            'rut': self.user.rut,
            'email': self.user.email,
            'cargo': self.user.cargo.nombre if self.user.cargo else None,
        }

        return data

class SupervisorSerializer(serializers.ModelSerializer):
    cargo = serializers.CharField(source='cargo.nombre', read_only=True)
    class Meta:
        model = Usuario
        fields = ['id', 'nombres', 'apellidos', 'email', 'cargo', 'rut']