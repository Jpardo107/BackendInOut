from django.db import models
from django.utils.text import slugify


class Zona(models.Model):
    codigo = models.SlugField(max_length=50, unique=True)
    nombre = models.CharField(max_length=100, unique=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("nombre", "id")

    def save(self, *args, **kwargs):
        self.codigo = slugify(self.codigo or self.nombre)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre

class Instalacion(models.Model):
    ESTADO_DIRECTIVA_CHOICES = [
        ("no_existe", "No existe"),
        ("vencida", "Vencida"),
        ("tramitada", "Tramitada"),
        ("rechazada", "Rechazada"),
        ("aprobada", "Aprobada"),
    ]
    nombre = models.CharField(max_length=255)
    direccion = models.CharField(max_length=255)
    comuna = models.CharField(max_length=100)
    nombre_contacto = models.CharField(max_length=255)
    correo_contacto = models.EmailField()
    telefono_contacto = models.CharField(max_length=20)
    zona = models.CharField(max_length=50, default='centro', db_index=True)
    estado_directiva = models.CharField(
        max_length=20,
        choices=ESTADO_DIRECTIVA_CHOICES,
        default="no_existe",
    )

    def __str__(self):
        return self.nombre
