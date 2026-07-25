from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework import serializers
from .models import PersonalEmpresa, Usuario
from .services.rut import formatear_rut, normalizar_rut


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


class PersonalEmpresaSerializer(serializers.ModelSerializer):
    rut_formateado = serializers.SerializerMethodField()
    instalacion_nombre = serializers.CharField(source='instalacion.nombre', read_only=True)

    class Meta:
        model = PersonalEmpresa
        fields = [
            'id',
            'rut',
            'rut_formateado',
            'nombre_completo',
            'ubicacion',
            'instalacion',
            'instalacion_nombre',
            'activo',
            'creado_en',
            'actualizado_en',
        ]
        read_only_fields = ['id', 'rut_formateado', 'instalacion_nombre', 'creado_en', 'actualizado_en']

    def get_rut_formateado(self, obj):
        return formatear_rut(obj.rut)

    def validate_rut(self, value):
        rut = normalizar_rut(value)
        if not rut:
            raise serializers.ValidationError("RUT invalido.")
        return rut

    def validate_nombre_completo(self, value):
        value = " ".join(str(value or "").split()).upper()
        if not value:
            raise serializers.ValidationError("El nombre es obligatorio.")
        return value

    def validate_ubicacion(self, value):
        return " ".join(str(value or "").split()).upper()

    def validate(self, attrs):
        attrs = super().validate(attrs)
        instalacion = attrs.get("instalacion")
        if self.instance is None and not instalacion:
            raise serializers.ValidationError({
                "instalacion": "Debes seleccionar una instalación."
            })
        if instalacion:
            attrs["ubicacion"] = instalacion.nombre.strip().upper()
        return attrs
