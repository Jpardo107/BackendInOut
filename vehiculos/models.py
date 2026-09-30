from django.conf import settings
from django.db import models


class Vehiculo(models.Model):
    patente = models.CharField(max_length=12, unique=True)
    marca = models.CharField(max_length=80)
    modelo = models.CharField(max_length=100)
    anio = models.PositiveSmallIntegerField(null=True, blank=True)
    kilometraje_actual = models.PositiveIntegerField(default=0)
    kilometraje_mantencion = models.PositiveIntegerField(null=True, blank=True)
    activo = models.BooleanField(default=True)
    supervisor_actual = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name="vehiculos_en_uso",
    )
    version = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["patente"]

    def __str__(self):
        return self.patente


class MovimientoVehiculo(models.Model):
    TIPOS = [("recepcion", "Recepción"), ("entrega", "Entrega")]
    solicitud_id = models.UUIDField(unique=True)
    vehiculo = models.ForeignKey(Vehiculo, on_delete=models.PROTECT, related_name="movimientos")
    supervisor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    supervisor_nombre = models.CharField(max_length=310)
    tipo = models.CharField(max_length=10, choices=TIPOS)
    kilometraje = models.PositiveIntegerField()
    gata = models.BooleanField()
    llave_cruz = models.BooleanField()
    extintor = models.BooleanField()
    triangulo = models.BooleanField()
    resumen = models.TextField(max_length=5000)
    creado_en = models.DateTimeField(auto_now_add=True)
    recepcion = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="entrega",
    )

    class Meta:
        ordering = ["-creado_en", "-id"]


class FotoVehiculo(models.Model):
    VISTAS = [(v, v.title()) for v in ("frontal", "trasera", "izquierdo", "derecho", "tablero", "extra")]
    movimiento = models.ForeignKey(MovimientoVehiculo, on_delete=models.CASCADE, related_name="fotos")
    vista = models.CharField(max_length=10, choices=VISTAS)
    storage_key = models.CharField(max_length=255)
    tiene_novedad = models.BooleanField(default=False)
    novedad = models.TextField(blank=True, max_length=3000)

    class Meta:
        ordering = ["id"]
