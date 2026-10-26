from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models


TIPOS = [
    ("coordinacion", "Coordinación"), ("traslado", "Traslado"),
    ("reunion", "Reunión"), ("administrativo", "Gestión administrativa"),
    ("personal", "Gestión de personal"), ("capacitacion", "Capacitación"),
    ("colacion", "Colación / pausa"), ("otro", "Otra actividad"),
    ("supervision", "Supervisión"),
    ("vestuario_equipo", "Vestuario y equipo"), ("cargo_fijo", "Cargo fijo"),
    ("utiles_aseo", "Útiles de aseo"), ("informe", "Informe"),
    ("gasto", "Rendición de gastos"), ("vehiculo", "Vehículo"),
]
JORNADAS = [("diurna", "Diurna"), ("nocturna", "Nocturna"), ("am", "AM"), ("pm", "PM")]


class Pauta(models.Model):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    inicio = models.DateField(help_text="Primer día de trabajo del ciclo; vigente desde esta fecha.")
    dias_trabajo = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(31)])
    dias_libres = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(31)])
    jornada = models.CharField(max_length=10, choices=JORNADAS)
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()

    class Meta:
        ordering = ["inicio"]
        constraints = [models.UniqueConstraint(fields=["usuario", "inicio"], name="plan_pauta_usuario_inicio")]


class DiaEspecial(models.Model):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    fecha = models.DateField()
    tipo = models.CharField(max_length=10, choices=[("extra", "Turno extra"), ("libre", "Libre"), ("trabajo", "Trabajo")])
    jornada = models.CharField(max_length=10, choices=JORNADAS, default="diurna")
    hora_inicio = models.TimeField(null=True, blank=True)
    hora_fin = models.TimeField(null=True, blank=True)
    nota = models.CharField(max_length=500, blank=True)
    realizado = models.BooleanField(default=False)

    class Meta:
        ordering = ["fecha"]
        constraints = [models.UniqueConstraint(fields=["usuario", "fecha"], name="plan_dia_usuario_fecha")]


class Actividad(models.Model):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    fecha = models.DateField()
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField(null=True, blank=True)
    tipo = models.CharField(max_length=30, choices=TIPOS)
    titulo = models.CharField(max_length=180)
    detalle = models.TextField(max_length=3000, blank=True)
    instalacion = models.ForeignKey("instalacion.Instalacion", on_delete=models.SET_NULL, null=True, blank=True)
    estado = models.CharField(max_length=12, choices=[("pendiente", "Planificada"), ("realizada", "Realizada"), ("cancelada", "Cancelada")], default="pendiente")
    # References are validated against the authenticated owner's actual source rows.
    registro_vinculado = models.CharField(max_length=80, blank=True)
    creada_en = models.DateTimeField(auto_now_add=True)
    actualizada_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["fecha", "hora_inicio", "id"]
        indexes = [models.Index(fields=["usuario", "fecha"], name="plan_actividad_usuario_fecha")]
