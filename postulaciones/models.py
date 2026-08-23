import secrets
import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class TipoInstalacionLaboral(models.Model):
    nombre = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    activo = models.BooleanField(default=True)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("orden", "nombre")

    def __str__(self):
        return self.nombre


class PostulacionGuardia(models.Model):
    ESTADOS = [
        ("borrador", "Borrador"), ("datos_incompletos", "Datos incompletos"),
        ("pendiente_documentos", "Pendiente de documentos"),
        ("evaluacion_pendiente", "Evaluación pendiente"), ("finalizada", "Finalizada"),
        ("en_revision", "En revisión"), ("preseleccionada", "Preseleccionada"),
        ("entrevista_agendada", "Entrevista agendada"), ("entrevistada", "Entrevistada"),
        ("seleccionada", "Seleccionada"), ("no_seleccionada", "No seleccionada"),
        ("banco_postulantes", "Banco de postulantes"), ("desistida", "Desistida"),
    ]
    OS10_ESTADOS = [
        ("vigente", "Vigente"), ("vencido", "Vencido"),
        ("en_proceso", "En proceso"), ("no_tiene", "No tiene"),
    ]

    id_publico = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    codigo = models.CharField(max_length=20, unique=True, blank=True)
    acceso_hash = models.CharField(max_length=128, editable=False)
    nombres = models.CharField(max_length=120)
    apellido_paterno = models.CharField(max_length=80)
    apellido_materno = models.CharField(max_length=80, blank=True)
    rut = models.CharField(max_length=12, db_index=True)
    fecha_nacimiento = models.DateField(null=True, blank=True)
    nacionalidad = models.CharField(max_length=80, blank=True)
    telefono = models.CharField(max_length=20)
    email = models.EmailField(db_index=True)
    comuna_residencia = models.CharField(max_length=100)
    direccion = models.CharField(max_length=255, blank=True)
    situacion_migratoria = models.CharField(max_length=120, blank=True)
    tiene_licencia = models.BooleanField(default=False)
    clase_licencia = models.CharField(max_length=30, blank=True)
    movilizacion_propia = models.BooleanField(default=False)
    disponibilidad_incorporacion = models.DateField(null=True, blank=True)
    disponible_dia = models.BooleanField(default=False)
    disponible_noche = models.BooleanField(default=False)
    disponible_4x4 = models.BooleanField(default=False)
    disponible_5x2 = models.BooleanField(default=False)
    otras_disponibilidades = models.JSONField(default=list, blank=True)
    presentacion = models.TextField(blank=True, max_length=1500)
    estado_os10 = models.CharField(max_length=20, choices=OS10_ESTADOS, default="no_tiene")
    os10_vencimiento = models.DateField(null=True, blank=True)
    os10_numero = models.CharField(max_length=100, blank=True)
    estado = models.CharField(max_length=30, choices=ESTADOS, default="borrador", db_index=True)
    paso_actual = models.PositiveSmallIntegerField(default=1)
    declaracion_veracidad = models.BooleanField(default=False)
    consentimiento_datos = models.BooleanField(default=False)
    version_consentimiento = models.CharField(max_length=30, blank=True)
    consentimiento_en = models.DateTimeField(null=True, blank=True)
    finalizada_en = models.DateTimeField(null=True, blank=True)
    reclutador_asignado = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="postulaciones_asignadas",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-creado_en",)
        constraints = [
            models.UniqueConstraint(
                fields=("rut", "email"),
                condition=models.Q(estado__in=("borrador", "datos_incompletos", "pendiente_documentos", "evaluacion_pendiente")),
                name="postulacion_activa_rut_email_unica",
            )
        ]
        indexes = [models.Index(fields=("estado", "creado_en")), models.Index(fields=("comuna_residencia",))]

    @property
    def nombre_completo(self):
        return " ".join(filter(None, (self.nombres, self.apellido_paterno, self.apellido_materno)))

    def save(self, *args, **kwargs):
        if not self.codigo:
            self.codigo = f"IN-{secrets.token_hex(4).upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.codigo} - {self.nombre_completo}"


class AntecedenteAcademicoPostulante(models.Model):
    ESTADOS = [("completo", "Completo"), ("incompleto", "Incompleto"), ("en_curso", "En curso")]
    postulacion = models.ForeignKey(PostulacionGuardia, on_delete=models.CASCADE, related_name="estudios")
    nivel_educacional = models.CharField(max_length=100)
    institucion = models.CharField(max_length=180)
    carrera_especialidad = models.CharField(max_length=180, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS)
    anio_inicio = models.PositiveSmallIntegerField(null=True, blank=True)
    anio_termino = models.PositiveSmallIntegerField(null=True, blank=True)
    observaciones = models.TextField(blank=True)


class CursoPostulante(models.Model):
    postulacion = models.ForeignKey(PostulacionGuardia, on_delete=models.CASCADE, related_name="cursos")
    nombre = models.CharField(max_length=180)
    institucion = models.CharField(max_length=180, blank=True)
    tipo_curso = models.CharField(max_length=100, blank=True)
    fecha_realizacion = models.DateField(null=True, blank=True)
    fecha_vencimiento = models.DateField(null=True, blank=True)
    estado = models.CharField(max_length=30, blank=True)
    numero_certificado = models.CharField(max_length=100, blank=True)
    observaciones = models.TextField(blank=True)


class ExperienciaLaboralPostulante(models.Model):
    postulacion = models.ForeignKey(PostulacionGuardia, on_delete=models.CASCADE, related_name="experiencias")
    empresa = models.CharField(max_length=180)
    cargo = models.CharField(max_length=120)
    tipo_instalacion = models.ForeignKey(TipoInstalacionLaboral, null=True, blank=True, on_delete=models.SET_NULL)
    comuna = models.CharField(max_length=100, blank=True)
    fecha_inicio = models.DateField()
    fecha_termino = models.DateField(null=True, blank=True)
    trabajo_actual = models.BooleanField(default=False)
    funciones = models.TextField()
    motivo_salida = models.CharField(max_length=255, blank=True)
    referencia_nombre = models.CharField(max_length=160, blank=True)
    referencia_telefono = models.CharField(max_length=20, blank=True)
    observaciones = models.TextField(blank=True)


class VacanteGuardia(models.Model):
    ESTADOS = [
        ("borrador", "Borrador"), ("publicado", "Publicado"), ("pausado", "Pausado"),
        ("completo", "Completo"), ("cerrado", "Cerrado"),
    ]
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    instalacion = models.ForeignKey("instalacion.Instalacion", on_delete=models.PROTECT, related_name="vacantes_guardia")
    tipo_instalacion = models.ForeignKey(TipoInstalacionLaboral, on_delete=models.PROTECT, related_name="vacantes")
    comuna_publica = models.CharField(max_length=100)
    descripcion_publica = models.CharField(max_length=220)
    jornada = models.CharField(max_length=80)
    sistema_turno = models.CharField(max_length=80)
    hora_entrada = models.TimeField(null=True, blank=True)
    hora_salida = models.TimeField(null=True, blank=True)
    sueldo = models.PositiveIntegerField()
    sueldo_liquido = models.BooleanField(default=True)
    beneficios = models.TextField(blank=True)
    requisitos = models.TextField(blank=True)
    cantidad_cupos = models.PositiveSmallIntegerField(default=1)
    cupos_ocupados = models.PositiveSmallIntegerField(default=0)
    fecha_inicio = models.DateField(null=True, blank=True)
    fecha_fin_publicacion = models.DateField(null=True, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default="borrador", db_index=True)
    permite_postulaciones = models.BooleanField(default=True)
    requiere_os10_vigente = models.BooleanField(default=False)
    requiere_licencia = models.BooleanField(default=False)
    requiere_movilizacion = models.BooleanField(default=False)
    observaciones_internas = models.TextField(blank=True)
    prioridad = models.PositiveSmallIntegerField(default=0)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("prioridad", "-creado_en")

    @property
    def disponibles(self):
        return max(self.cantidad_cupos - self.cupos_ocupados, 0)


class PreferenciaVacantePostulante(models.Model):
    postulacion = models.ForeignKey(PostulacionGuardia, on_delete=models.CASCADE, related_name="preferencias")
    vacante = models.ForeignKey(VacanteGuardia, on_delete=models.PROTECT, related_name="interesados")
    orden_preferencia = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(3)])
    estado_interes = models.CharField(max_length=30, default="interesado")
    seleccionada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("postulacion", "vacante"), name="preferencia_vacante_unica"),
            models.UniqueConstraint(fields=("postulacion", "orden_preferencia"), name="orden_preferencia_unico"),
        ]


class PreguntaPostulacion(models.Model):
    TIPOS = [
        ("unica", "Selección única"), ("multiple", "Selección múltiple"),
        ("texto_corto", "Texto corto"), ("texto_largo", "Texto largo"),
        ("booleano", "Verdadero o falso"), ("escala", "Escala"),
        ("situacional", "Caso situacional"),
    ]
    texto = models.TextField()
    tipo_instalacion = models.ForeignKey(TipoInstalacionLaboral, null=True, blank=True, on_delete=models.CASCADE, related_name="preguntas")
    tipo_respuesta = models.CharField(max_length=30, choices=TIPOS)
    opciones = models.JSONField(default=list, blank=True)
    respuesta_correcta = models.JSONField(null=True, blank=True)
    puntaje = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    dificultad = models.CharField(max_length=30, default="media")
    activo = models.BooleanField(default=True)
    orden = models.PositiveSmallIntegerField(default=0)
    obligatoria = models.BooleanField(default=True)
    explicacion_interna = models.TextField(blank=True)
    etiquetas = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ("orden", "id")


class EvaluacionPostulacion(models.Model):
    postulacion = models.OneToOneField(PostulacionGuardia, on_delete=models.CASCADE, related_name="evaluacion")
    iniciada_en = models.DateTimeField(auto_now_add=True)
    finalizada_en = models.DateTimeField(null=True, blank=True)
    puntaje = models.DecimalField(max_digits=8, decimal_places=2, default=0)


class PreguntaAsignadaEvaluacion(models.Model):
    evaluacion = models.ForeignKey(EvaluacionPostulacion, on_delete=models.CASCADE, related_name="preguntas_asignadas")
    pregunta_origen = models.ForeignKey(PreguntaPostulacion, null=True, on_delete=models.SET_NULL)
    texto = models.TextField()
    tipo_respuesta = models.CharField(max_length=30)
    opciones = models.JSONField(default=list, blank=True)
    respuesta_correcta = models.JSONField(null=True, blank=True)
    puntaje = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    obligatoria = models.BooleanField(default=True)
    tipo_instalacion_nombre = models.CharField(max_length=120, blank=True)
    orden = models.PositiveSmallIntegerField(default=0)


class RespuestaPostulacion(models.Model):
    pregunta_asignada = models.OneToOneField(PreguntaAsignadaEvaluacion, on_delete=models.CASCADE, related_name="respuesta")
    respuesta = models.JSONField()
    puntaje_obtenido = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    respondida_en = models.DateTimeField(auto_now=True)


class DocumentoPostulacion(models.Model):
    TIPOS = [
        ("cedula_frontal", "Cédula frontal"),
        ("cedula_posterior", "Cédula posterior"),
        ("certificado_os10", "Certificado OS10"),
        ("curriculum", "Currículum"),
        ("certificado_estudios", "Certificado de estudios"),
        ("licencia_conducir", "Licencia de conducir"),
        ("documentacion_migratoria", "Documentación migratoria"),
        ("otro", "Otro antecedente"),
    ]
    ESTADOS = [
        ("cargado", "Cargado"), ("pendiente_revision", "Pendiente de revisión"),
        ("validado", "Validado"), ("rechazado", "Rechazado"), ("vencido", "Vencido"),
    ]
    postulacion = models.ForeignKey(PostulacionGuardia, on_delete=models.CASCADE, related_name="documentos")
    curso = models.ForeignKey(CursoPostulante, null=True, blank=True, on_delete=models.SET_NULL, related_name="documentos")
    tipo_documento = models.CharField(max_length=60, choices=TIPOS)
    nombre_original = models.CharField(max_length=255)
    storage_key = models.CharField(max_length=500, db_index=True)
    mime_type = models.CharField(max_length=120)
    size = models.PositiveIntegerField()
    estado = models.CharField(max_length=30, choices=ESTADOS, default="pendiente_revision")
    fecha_vencimiento = models.DateField(null=True, blank=True)
    observaciones = models.TextField(blank=True)
    validado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    validado_en = models.DateTimeField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    @property
    def nombre_documento(self):
        return self.get_tipo_documento_display()


class ClaveTemporalPostulacion(models.Model):
    rut = models.CharField(max_length=12, db_index=True)
    email = models.EmailField()
    codigo_hash = models.CharField(max_length=128)
    expira_en = models.DateTimeField()
    intentos = models.PositiveSmallIntegerField(default=0)
    usada_en = models.DateTimeField(null=True, blank=True)
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-creada_en",)


class TokenQrPostulacion(models.Model):
    postulacion = models.OneToOneField(PostulacionGuardia, on_delete=models.CASCADE, related_name="token_qr")
    token = models.CharField(max_length=128, unique=True, default=secrets.token_urlsafe)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    ultimo_uso = models.DateTimeField(null=True, blank=True)


class ObservacionPostulacion(models.Model):
    postulacion = models.ForeignKey(PostulacionGuardia, on_delete=models.CASCADE, related_name="observaciones_internas")
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    texto = models.TextField()
    creado_en = models.DateTimeField(auto_now_add=True)


class HistorialPostulacion(models.Model):
    postulacion = models.ForeignKey(PostulacionGuardia, on_delete=models.CASCADE, related_name="historial")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    accion = models.CharField(max_length=80)
    detalle = models.JSONField(default=dict, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)


class EntrevistaPostulacion(models.Model):
    postulacion = models.ForeignKey(PostulacionGuardia, on_delete=models.CASCADE, related_name="entrevistas")
    fecha = models.DateTimeField()
    entrevistador = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    modalidad = models.CharField(max_length=60, blank=True)
    resultado = models.CharField(max_length=120, blank=True)
    observaciones = models.TextField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
