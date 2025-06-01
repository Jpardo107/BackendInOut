from django.db import models
from user.models import Usuario
from instalacion.models import Instalacion


class Supervision(models.Model):
    ESTADO_SOLICITUD_CHOICES = [
        ('pendiente', 'Pendiente'),  # Valor por defecto al crear
        ('gestionado', 'Gestionado'),
        ('entregado', 'Entregado'),
        ('denegado', 'Denegado'),
    ]
    instalacion = models.ForeignKey(Instalacion, on_delete=models.CASCADE, related_name='supervisiones')
    supervisor = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, related_name='supervisiones')
    fecha = models.DateField()
    hora_inicio = models.TimeField()
    hora_final = models.TimeField()
    novedades = models.TextField(blank=True, null=True)
    solicitudes = models.TextField(blank=True, null=True)
    latitud = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitud = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    estado_solicitud = models.CharField(
        max_length=20,
        choices=ESTADO_SOLICITUD_CHOICES,
        default='pendiente',  # Valor predeterminado
    )


    def __str__(self):
        supervisor_nombre = f"{self.supervisor.nombres} {self.supervisor.apellidos}" if self.supervisor else "Sin supervisor"
        return f"Supervisión en {self.instalacion.nombre} por {supervisor_nombre} - {self.fecha}"


class FotoSupervision(models.Model):
    supervision = models.ForeignKey('Supervision', on_delete=models.CASCADE, related_name='fotos')
    url_imagen = models.URLField()
    descripcion = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Foto Supervision {self.supervision.id} - {self.url_imagen}"
