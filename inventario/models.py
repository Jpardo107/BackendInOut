from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from .services.codigos import generar_codigo_barra, generar_codigo_qr, normalizar_texto


class PrendaInventario(models.Model):
    nombre_prenda = models.CharField(max_length=120)
    nombre_normalizado = models.CharField(max_length=120, editable=False)
    talla_prenda = models.CharField(max_length=40)
    talla_normalizada = models.CharField(max_length=40, editable=False)
    cantidad_prenda = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    stock_actual = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    stock_critico = models.PositiveIntegerField(default=5, validators=[MinValueValidator(0)])
    codigo_barra = models.CharField(max_length=80, unique=True, db_index=True)
    codigo_qr = models.CharField(max_length=255, unique=True)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nombre_normalizado", "talla_normalizada"]
        constraints = [
            models.UniqueConstraint(
                fields=["nombre_normalizado", "talla_normalizada"],
                name="unique_prenda_talla_normalizada",
            ),
            models.CheckConstraint(
                check=models.Q(stock_actual__gte=0),
                name="inventario_stock_actual_no_negativo",
            ),
        ]
        indexes = [
            models.Index(fields=["nombre_normalizado", "talla_normalizada"]),
            models.Index(fields=["stock_actual"]),
        ]

    @property
    def bajo_stock_critico(self):
        return self.stock_actual <= self.stock_critico

    def save(self, *args, **kwargs):
        self.nombre_normalizado = normalizar_texto(self.nombre_prenda)
        self.talla_normalizada = normalizar_texto(self.talla_prenda)
        self.codigo_barra = generar_codigo_barra(self.nombre_prenda, self.talla_prenda)
        self.codigo_qr = generar_codigo_qr(self.codigo_barra)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nombre_prenda} - {self.talla_prenda}"


class MovimientoInventario(models.Model):
    TIPO_INGRESO = "ingreso"
    TIPO_ENTREGA = "entrega"
    TIPO_RECEPCION = "recepcion"
    TIPO_AJUSTE = "ajuste"

    TIPO_CHOICES = [
        (TIPO_INGRESO, "Ingreso desde proveedor"),
        (TIPO_ENTREGA, "Entrega a usuario final"),
        (TIPO_RECEPCION, "Recepcion/devolucion"),
        (TIPO_AJUSTE, "Ajuste de inventario"),
    ]

    ESTADO_NO_APLICA = "no_aplica"
    ESTADO_EN_TRANSITO = "en_transito"
    ESTADO_RECIBIDO = "recibido"
    ESTADO_DEVUELTO = "devuelto"
    ESTADO_CANCELADO = "cancelado"

    ESTADO_ENVIO_CHOICES = [
        (ESTADO_NO_APLICA, "No aplica"),
        (ESTADO_EN_TRANSITO, "En transito"),
        (ESTADO_RECIBIDO, "Recibido"),
        (ESTADO_DEVUELTO, "Devuelto"),
        (ESTADO_CANCELADO, "Cancelado"),
    ]

    prenda = models.ForeignKey(
        PrendaInventario,
        on_delete=models.PROTECT,
        related_name="movimientos",
    )
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    cantidad = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    stock_antes = models.PositiveIntegerField(validators=[MinValueValidator(0)])
    stock_despues = models.PositiveIntegerField(validators=[MinValueValidator(0)])
    usuario_registro = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movimientos_inventario",
    )
    usuario_final = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prendas_recibidas",
    )
    observacion = models.TextField(blank=True)
    estado_envio = models.CharField(
        max_length=20,
        choices=ESTADO_ENVIO_CHOICES,
        default=ESTADO_NO_APLICA,
        db_index=True,
    )
    fecha_estado_envio = models.DateTimeField(default=timezone.now)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado_en", "-id"]
        indexes = [
            models.Index(fields=["tipo", "creado_en"]),
            models.Index(fields=["prenda", "creado_en"]),
            models.Index(fields=["estado_envio", "creado_en"]),
        ]

    def __str__(self):
        return f"{self.tipo} {self.cantidad} - {self.prenda}"
