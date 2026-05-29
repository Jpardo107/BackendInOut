import os
import uuid

from django.conf import settings
from django.db import models

from instalacion.models import Instalacion


def reporte_imagen_upload_key(reporte_id: int, original_name: str) -> str:
    _, ext = os.path.splitext(original_name or "")
    ext = ext.lower()
    return f"reportes/reporte_{reporte_id}/imagenes/{uuid.uuid4().hex}{ext}"


def reporte_archivo_origen_upload_key(reporte_id: int, original_name: str) -> str:
    _, ext = os.path.splitext(original_name or "")
    ext = ext.lower()
    return f"reportes/reporte_{reporte_id}/archivo_origen/{uuid.uuid4().hex}{ext}"


class ReporteInforme(models.Model):
    TIPO_PRE_INFORME = "pre_informe"
    TIPO_VULNERABILIDADES = "vulnerabilidades"
    TIPO_REPORTE_CHOICES = (
        (TIPO_PRE_INFORME, "Pre informe"),
        (TIPO_VULNERABILIDADES, "Reporte de vulnerabilidades"),
    )

    CRITICIDAD_CHOICES = (
        ("baja", "Baja"),
        ("media", "Media"),
        ("alta", "Alta"),
        ("critica", "Critica"),
    )

    ESTADO_BORRADOR = "borrador"
    ESTADO_PROCESANDO_IA = "procesando_ia"
    ESTADO_GENERADO = "generado"
    ESTADO_ERROR_IA = "error_ia"
    ESTADO_CHOICES = (
        (ESTADO_BORRADOR, "Borrador"),
        (ESTADO_PROCESANDO_IA, "Procesando IA"),
        (ESTADO_GENERADO, "Generado"),
        (ESTADO_ERROR_IA, "Error IA"),
    )

    tipo_reporte = models.CharField(max_length=30, choices=TIPO_REPORTE_CHOICES)
    instalacion = models.ForeignKey(
        Instalacion,
        on_delete=models.PROTECT,
        related_name="reportes_informes",
    )
    zona = models.CharField(max_length=80, blank=True, default="")
    usuario_creador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="reportes_informes",
    )
    autor_nombre = models.CharField(max_length=255)
    autor_cargo = models.CharField(max_length=150, blank=True, default="")
    descripcion_hechos = models.TextField(blank=True, default="")
    analisis_previo = models.TextField(blank=True, default="")
    analisis_final_usuario = models.TextField(blank=True, default="")
    personal_presente = models.TextField(blank=True, default="")
    personal_policial_presente = models.BooleanField(default=False)
    carabinero_cargo = models.CharField(max_length=150, blank=True, default="")
    patente_patrulla = models.CharField(max_length=30, blank=True, default="")
    numero_carro_policial = models.CharField(max_length=30, blank=True, default="")
    criticidad_general = models.CharField(
        max_length=20,
        choices=CRITICIDAD_CHOICES,
        blank=True,
        default="",
    )
    resumen_ejecutivo = models.TextField(blank=True, default="")
    conclusion_profesional = models.TextField(blank=True, default="")
    riesgos_detectados = models.JSONField(default=list, blank=True)
    recomendaciones_ia = models.JSONField(default=list, blank=True)
    matriz_riesgo = models.JSONField(default=list, blank=True)
    texto_final_pdf = models.TextField(blank=True, default="")
    respuesta_ia_raw = models.JSONField(null=True, blank=True)
    archivo_origen_storage_key = models.CharField(max_length=500, blank=True, default="")
    archivo_origen_nombre = models.CharField(max_length=255, blank=True, default="")
    archivo_origen_mime_type = models.CharField(max_length=120, blank=True, default="")
    archivo_origen_size = models.PositiveIntegerField(default=0)
    texto_extraido_origen = models.TextField(blank=True, default="")
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default=ESTADO_BORRADOR)
    fecha_emision = models.DateField()
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-creado_en", "-id")

    def __str__(self):
        return f"{self.get_tipo_reporte_display()} - {self.instalacion} - {self.fecha_emision}"


class ImagenReporteInforme(models.Model):
    reporte = models.ForeignKey(
        ReporteInforme,
        on_delete=models.CASCADE,
        related_name="imagenes",
    )
    storage_key = models.CharField(max_length=500, unique=True)
    nombre_original = models.CharField(max_length=255, blank=True, default="")
    mime_type = models.CharField(max_length=120, blank=True, default="")
    size = models.PositiveIntegerField(default=0)
    descripcion = models.TextField(blank=True, default="")
    recomendacion_usuario = models.TextField(blank=True, default="")
    orden = models.PositiveIntegerField(default=0)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("orden", "id")
        unique_together = ("reporte", "orden")

    def __str__(self):
        return f"Imagen {self.orden} reporte {self.reporte_id}"
