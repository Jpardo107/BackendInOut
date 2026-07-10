from django.conf import settings
from django.db import models

from instalacion.models import Instalacion
from user.models import PersonalEmpresa


class DocumentoLaboral(models.Model):
    CONTRATO = "contrato"
    RIOHS = "riohs"
    TIPOS = ((CONTRATO, "Contrato de trabajo"), (RIOHS, "Reglamento interno (RIOHS)"))

    tipo = models.CharField(max_length=20, choices=TIPOS)
    nombre_original = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=120, blank=True)
    size = models.PositiveIntegerField(default=0)
    storage_key = models.CharField(max_length=500, unique=True)
    texto_extraido = models.TextField()
    activo = models.BooleanField(default=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="documentos_laborales"
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-creado_en",)


class Amonestacion(models.Model):
    persona = models.ForeignKey(PersonalEmpresa, on_delete=models.PROTECT, related_name="amonestaciones")
    instalacion = models.ForeignKey(Instalacion, on_delete=models.PROTECT, related_name="amonestaciones")
    fecha_hecho = models.DateField()
    supervisor = models.CharField(max_length=220)
    tipo_incumplimiento = models.CharField(max_length=180)
    descripcion = models.TextField()
    reincidencia = models.BooleanField(default=False)
    antecedentes = models.TextField(blank=True)
    ciudad = models.CharField(max_length=120, default="Santiago")
    contrato = models.ForeignKey(DocumentoLaboral, on_delete=models.PROTECT, related_name="amonestaciones_contrato")
    riohs = models.ForeignKey(DocumentoLaboral, on_delete=models.PROTECT, related_name="amonestaciones_riohs")
    carta = models.TextField()
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="amonestaciones_creadas"
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-creado_en",)

