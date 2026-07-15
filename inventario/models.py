import os
import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from .services.codigos import generar_codigo_barra, generar_codigo_qr, normalizar_texto


class PrendaInventario(models.Model):
    CATEGORIA_VESTUARIO = "vestuario_equipo"
    CATEGORIA_CARGO_FIJO = "cargo_fijo"
    CATEGORIA_CHOICES = [
        (CATEGORIA_VESTUARIO, "Vestuario y equipo"),
        (CATEGORIA_CARGO_FIJO, "Cargo fijo"),
    ]

    categoria = models.CharField(
        max_length=30,
        choices=CATEGORIA_CHOICES,
        default=CATEGORIA_VESTUARIO,
        db_index=True,
    )
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
                fields=["categoria", "nombre_normalizado", "talla_normalizada"],
                name="unique_categoria_prenda_talla_normalizada",
            ),
            models.CheckConstraint(
                check=models.Q(stock_actual__gte=0),
                name="inventario_stock_actual_no_negativo",
            ),
        ]
        indexes = [
            models.Index(fields=["categoria", "nombre_normalizado", "talla_normalizada"], name="inventario_categori_30ca1b_idx"),
            models.Index(fields=["stock_actual"]),
        ]

    @property
    def bajo_stock_critico(self):
        return self.stock_actual <= self.stock_critico

    def save(self, *args, **kwargs):
        self.nombre_normalizado = normalizar_texto(self.nombre_prenda)
        self.talla_normalizada = normalizar_texto(self.talla_prenda)
        nombre_codigo = (
            f"CARGO FIJO {self.nombre_prenda}"
            if self.categoria == self.CATEGORIA_CARGO_FIJO
            else self.nombre_prenda
        )
        self.codigo_barra = generar_codigo_barra(nombre_codigo, self.talla_prenda)
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
    destinatario_personal = models.ForeignKey(
        "user.PersonalEmpresa",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movimientos_inventario",
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


def comprobante_entrega_upload_key(original_name: str) -> str:
    _, ext = os.path.splitext(original_name or "")
    ext = ext.lower()[:10] or ".pdf"
    return f"inventario/comprobantes/{uuid.uuid4().hex}{ext}"


class ComprobanteEntregaInventario(models.Model):
    movimientos = models.ManyToManyField(
        MovimientoInventario,
        related_name="comprobantes_entrega",
    )
    destinatario_personal = models.ForeignKey(
        "user.PersonalEmpresa",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comprobantes_inventario",
    )
    supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comprobantes_inventario_supervisados",
    )
    storage_key = models.CharField(max_length=500, unique=True)
    nombre_original = models.CharField(max_length=255, blank=True, default="")
    mime_type = models.CharField(max_length=120, blank=True, default="application/pdf")
    size = models.PositiveIntegerField(default=0)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado_en", "-id"]
        indexes = [
            models.Index(fields=["creado_en"]),
            models.Index(fields=["destinatario_personal", "creado_en"]),
            models.Index(fields=["supervisor", "creado_en"]),
        ]

    def __str__(self):
        return self.nombre_original or f"Comprobante inventario {self.id}"


class AutorizacionEntregaInventario(models.Model):
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="autorizacion_entrega_inventario",
    )
    autorizado = models.BooleanField(default=False)
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="autorizaciones_entrega_inventario_actualizadas",
    )
    actualizado_en = models.DateTimeField(auto_now=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["usuario__nombres", "usuario__apellidos"]

    def __str__(self):
        estado = "autorizado" if self.autorizado else "no autorizado"
        return f"{self.usuario} - {estado}"


class ConfiguracionAlertaStock(models.Model):
    email_1 = models.EmailField(blank=True, default="")
    email_2 = models.EmailField(blank=True, default="")
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="configuraciones_alerta_stock_actualizadas",
    )
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuración de alerta de stock"
        verbose_name_plural = "Configuración de alertas de stock"

    @property
    def destinatarios(self):
        return [email for email in (self.email_1, self.email_2) if email]


class RegistroAlertaStock(models.Model):
    prenda = models.ForeignKey(
        PrendaInventario,
        on_delete=models.CASCADE,
        related_name="alertas_stock",
    )
    movimiento = models.ForeignKey(
        MovimientoInventario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alertas_stock",
    )
    stock_actual = models.PositiveIntegerField()
    stock_critico = models.PositiveIntegerField()
    destinatarios = models.JSONField(default=list)
    enviado = models.BooleanField(default=False)
    error = models.TextField(blank=True, default="")
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-creado_en", "-id")
