from django.db import models

class Instalacion(models.Model):
    ZONAS_CHOICES = [
        ('norte', 'Norte'),
        ('centro', 'Centro'),
        ('sur', 'Sur'),
        ('tw', 'Tw'),
    ]
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
    zona = models.CharField(max_length=10, choices=ZONAS_CHOICES, default='centro')  # ✨ nuevo campo
    estado_directiva = models.CharField(
        max_length=20,
        choices=ESTADO_DIRECTIVA_CHOICES,
        default="no_existe",
    )

    def __str__(self):
        return self.nombre
