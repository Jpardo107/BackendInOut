from django.db import models

class Instalacion(models.Model):
    ZONAS_CHOICES = [
        ('norte', 'Norte'),
        ('centro', 'Centro'),
        ('sur', 'Sur'),
        ('tw', 'Tw'),
    ]
    nombre = models.CharField(max_length=255)
    direccion = models.CharField(max_length=255)
    comuna = models.CharField(max_length=100)
    nombre_contacto = models.CharField(max_length=255)
    correo_contacto = models.EmailField()
    telefono_contacto = models.CharField(max_length=20)
    zona = models.CharField(max_length=10, choices=ZONAS_CHOICES, default='centro')  # ✨ nuevo campo

    def __str__(self):
        return self.nombre
