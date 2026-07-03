from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models


# Tabla Cargo
class Cargo(models.Model):
    nombre = models.CharField(max_length=100)

    def __str__(self):
        return self.nombre


# Manager personalizado
class UsuarioManager(BaseUserManager):
    def create_user(self, username, password=None, **extra_fields):
        if not username:
            raise ValueError('El nombre de usuario es obligatorio')
        user = self.model(username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(username, password, **extra_fields)


# Tabla Usuario (modelo personalizado)
class Usuario(AbstractBaseUser, PermissionsMixin):
    username = models.CharField(max_length=150, unique=True)
    nombres = models.CharField(max_length=150)
    apellidos = models.CharField(max_length=150)
    rut = models.CharField(max_length=12, unique=True)
    email = models.EmailField(unique=True)
    cargo = models.ForeignKey(Cargo, on_delete=models.SET_NULL, null=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = UsuarioManager()

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['nombres', 'apellidos', 'rut', 'email']

    def __str__(self):
        return f"{self.nombres} {self.apellidos}"


class PersonalEmpresa(models.Model):
    rut = models.CharField(max_length=12, unique=True, db_index=True)
    nombre_completo = models.CharField(max_length=220)
    ubicacion = models.CharField(max_length=160, blank=True)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nombre_completo"]
        indexes = [
            models.Index(fields=["ubicacion"]),
            models.Index(fields=["activo"]),
        ]

    def __str__(self):
        return f"{self.nombre_completo} - {self.rut}"
