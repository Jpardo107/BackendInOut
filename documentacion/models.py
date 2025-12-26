from django.db import models
from supervision.models import Supervision

import os
import uuid
from django.conf import settings
from instalacion.models import Instalacion

class DocumentoItem(models.Model):
    nombre = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.nombre

class EstadoDocumentacion(models.Model):
    supervision = models.ForeignKey(Supervision, on_delete=models.CASCADE, related_name="estado_documentos")
    documento = models.ForeignKey(DocumentoItem, on_delete=models.CASCADE)
    cantidad_revisada = models.PositiveIntegerField(default=0)
    validez = models.BooleanField(default=True)  # 👈 True = Vigente / False = Vencido

    def __str__(self):
        estado_validez = "Vigente" if self.validez else "Vencido"
        return f"{self.supervision.id} - {self.documento.nombre} ({estado_validez})"


def documento_upload_key(instalacion_id: int, original_name: str) -> str:
    # Mantiene extensión original si existe
    _, ext = os.path.splitext(original_name or "")
    ext = ext.lower()[:10]  # seguridad básica
    return f"documentos/instalacion_{instalacion_id}/{uuid.uuid4().hex}{ext}"


class DocumentoInstalacion(models.Model):
    CLASIFICACION_CHOICES = (
        ("interno", "Interno"),
        ("confidencial", "Confidencial"),
    )

    instalacion = models.ForeignKey(
        Instalacion,
        on_delete=models.CASCADE,
        related_name="documentos",
    )

    titulo = models.CharField(max_length=150)
    categoria = models.CharField(max_length=80, blank=True, default="")
    clasificacion = models.CharField(
        max_length=20,
        choices=CLASIFICACION_CHOICES,
        default="confidencial",
    )

    # En R2 guardamos SOLO la key, NO url
    storage_key = models.CharField(max_length=500, unique=True)

    nombre_original = models.CharField(max_length=255, blank=True, default="")
    mime_type = models.CharField(max_length=120, blank=True, default="")
    size = models.PositiveIntegerField(default=0)

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documentos_subidos",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"[{self.instalacion_id}] {self.titulo}"