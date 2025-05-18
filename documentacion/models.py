from django.db import models
from supervision.models import Supervision

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
