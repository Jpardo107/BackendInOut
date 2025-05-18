#cargo_fijo/models.py
from django.db import models
from supervision.models import Supervision


class CargoFijoItem(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    cantidad = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.nombre

class EstadoCargoFijo(models.Model):
    ESTADO_CHOICES = [
        ("buen estado", "Buen estado"),
        ("mal estado", "Mal estado"),
        ("inutilizable", "Inutilizable"),
    ]
    supervision = models.ForeignKey(Supervision, on_delete=models.CASCADE, related_name="estado_cargos_fijos")
    cargo_fijo = models.ForeignKey('CargoFijoItem', on_delete=models.CASCADE)
    cantidad_revisada = models.PositiveIntegerField(default=0)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="buen estado")

    def __str__(self):
        return f"{self.supervision.id} - {self.cargo_fijo.nombre} (Revisados: {self.cantidad_revisada})"
