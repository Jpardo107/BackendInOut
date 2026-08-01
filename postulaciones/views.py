import hashlib
import logging
import secrets
import uuid

from django.conf import settings
from django.db import IntegrityError, models, transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from documentacion.services.r2_storage import delete_document, upload_document
from .models import (
    AntecedenteAcademicoPostulante,
    CursoPostulante,
    DocumentoPostulacion,
    EntrevistaPostulacion,
    EvaluacionPostulacion,
    ExperienciaLaboralPostulante,
    HistorialPostulacion,
    ObservacionPostulacion,
    PostulacionGuardia,
    PreferenciaVacantePostulante,
    PreguntaAsignadaEvaluacion,
    PreguntaPostulacion,
    RespuestaPostulacion,
    TipoInstalacionLaboral,
    TokenQrPostulacion,
    VacanteGuardia,
)
from .permissions import IsPostulacionesAdmin
from .serializers import (
    CursoSerializer,
    DocumentoAdminSerializer,
    DocumentoPublicoSerializer,
    EntrevistaSerializer,
    EstudioSerializer,
    ExperienciaSerializer,
    ObservacionSerializer,
    PostulacionAdminDetalleSerializer,
    PostulacionAdminListSerializer,
    PostulacionPublicaSerializer,
    PreguntaAdminSerializer,
    PreguntaPublicaSerializer,
    TipoInstalacionSerializer,
    VacanteAdminSerializer,
    VacantePublicaSerializer,
)


EDITABLE_STATES = {"borrador", "datos_incompletos", "pendiente_documentos", "evaluacion_pendiente"}
ALLOWED_MIME = {
    "application/pdf": (b"%PDF",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
}
logger = logging.getLogger(__name__)


def token_hash(raw):
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")) or None


def audit(postulacion, accion, request, detalle=None):
    HistorialPostulacion.objects.create(
        postulacion=postulacion,
        usuario=request.user if request.user and request.user.is_authenticated else None,
        accion=accion,
        detalle=detalle or {},
        ip=client_ip(request),
    )


class PublicPostulacionViewSet(viewsets.ViewSet):
    permission_classes = [AllowAny]
    authentication_classes = []
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def _get_postulacion(self, request, public_id, editable=False):
        try:
            postulacion = PostulacionGuardia.objects.get(id_publico=public_id)
        except (PostulacionGuardia.DoesNotExist, ValueError):
            raise NotFound("Postulación no encontrada.")
        raw = request.headers.get("X-Postulacion-Token", "")
        if not raw or not secrets.compare_digest(postulacion.acceso_hash, token_hash(raw)):
            raise PermissionDenied("Token de postulación inválido.")
        if editable and postulacion.estado not in EDITABLE_STATES:
            raise ValidationError({"detail": "La postulación ya no admite modificaciones."})
        return postulacion

    @action(detail=False, methods=["post"], url_path="iniciar")
    def iniciar(self, request):
        rut = request.data.get("rut", "")
        email = str(request.data.get("email", "")).strip().lower()
        active = PostulacionGuardia.objects.filter(rut=rut.replace(".", "").replace("-", "").upper(), email__iexact=email, estado__in=EDITABLE_STATES).first()
        if active:
            return Response(
                {"detail": "Ya existe una postulación activa. Usa tu código y token guardado para continuar.", "codigo": active.codigo},
                status=status.HTTP_409_CONFLICT,
            )
        raw_token = secrets.token_urlsafe(32)
        serializer = PostulacionPublicaSerializer(data=request.data, partial=False)
        serializer.is_valid(raise_exception=True)
        postulacion = serializer.save(acceso_hash=token_hash(raw_token), email=email)
        audit(postulacion, "inicio_postulacion", request)
        return Response(
            {"postulacion": PostulacionPublicaSerializer(postulacion).data, "access_token": raw_token},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"], url_path="recuperar")
    def recuperar(self, request):
        codigo = str(request.data.get("codigo", "")).strip().upper()
        rut = str(request.data.get("rut", "")).replace(".", "").replace("-", "").upper()
        email = str(request.data.get("email", "")).strip().lower()
        try:
            postulacion = PostulacionGuardia.objects.get(codigo=codigo, rut=rut, email__iexact=email)
        except PostulacionGuardia.DoesNotExist:
            raise ValidationError({"detail": "No fue posible validar esos antecedentes."})
        if postulacion.estado not in EDITABLE_STATES:
            raise ValidationError({"detail": "Esta postulación ya fue finalizada."})
        raw_token = secrets.token_urlsafe(32)
        postulacion.acceso_hash = token_hash(raw_token)
        postulacion.save(update_fields=("acceso_hash", "actualizado_en"))
        audit(postulacion, "recuperacion_postulacion", request)
        return Response({"postulacion": PostulacionPublicaSerializer(postulacion).data, "access_token": raw_token})

    def retrieve(self, request, pk=None):
        postulacion = self._get_postulacion(request, pk)
        return Response(PostulacionPublicaSerializer(postulacion).data)

    def partial_update(self, request, pk=None):
        postulacion = self._get_postulacion(request, pk, editable=True)
        serializer = PostulacionPublicaSerializer(postulacion, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                serializer.save()
        except IntegrityError:
            logger.exception(
                "Conflicto de integridad al actualizar postulación %s",
                postulacion.id_publico,
            )
            raise ValidationError({
                "detail": "Ya existe otra postulación activa con este RUT y correo. Recupera esa postulación o utiliza los datos originales."
            })
        except Exception:
            logger.exception(
                "Error inesperado al actualizar postulación %s. Campos recibidos: %s",
                postulacion.id_publico,
                sorted(request.data.keys()),
            )
            raise
        return Response(PostulacionPublicaSerializer(postulacion).data)

    @action(detail=True, methods=["get", "post"], url_path="estudios")
    def estudios(self, request, pk=None):
        postulacion = self._get_postulacion(request, pk, editable=request.method == "POST")
        if request.method == "GET":
            return Response(EstudioSerializer(postulacion.estudios.all(), many=True).data)
        serializer = EstudioSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(postulacion=postulacion)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get", "post"], url_path="cursos")
    def cursos(self, request, pk=None):
        postulacion = self._get_postulacion(request, pk, editable=request.method == "POST")
        if request.method == "GET":
            return Response(CursoSerializer(postulacion.cursos.all(), many=True).data)
        serializer = CursoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(postulacion=postulacion)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get", "post"], url_path="experiencias")
    def experiencias(self, request, pk=None):
        postulacion = self._get_postulacion(request, pk, editable=request.method == "POST")
        if request.method == "GET":
            return Response(ExperienciaSerializer(postulacion.experiencias.all(), many=True).data)
        serializer = ExperienciaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(postulacion=postulacion)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch", "delete"], url_path=r"registro/(?P<tipo>estudios|cursos|experiencias)/(?P<registro_id>\d+)")
    def registro(self, request, pk=None, tipo=None, registro_id=None):
        postulacion = self._get_postulacion(request, pk, editable=True)
        config = {
            "estudios": (AntecedenteAcademicoPostulante, EstudioSerializer),
            "cursos": (CursoPostulante, CursoSerializer),
            "experiencias": (ExperienciaLaboralPostulante, ExperienciaSerializer),
        }
        model, serializer_class = config[tipo]
        try:
            instance = model.objects.get(pk=registro_id, postulacion=postulacion)
        except model.DoesNotExist:
            raise NotFound("Registro no encontrado.")
        if request.method == "DELETE":
            instance.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        serializer = serializer_class(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="catalogos/tipos-instalacion")
    def tipos_instalacion(self, request):
        return Response(TipoInstalacionSerializer(TipoInstalacionLaboral.objects.filter(activo=True), many=True).data)

    @action(detail=False, methods=["get"], url_path="vacantes")
    def vacantes(self, request):
        today = timezone.localdate()
        queryset = VacanteGuardia.objects.filter(
            estado="publicado", permite_postulaciones=True, cantidad_cupos__gt=models.F("cupos_ocupados"),
        ).filter(Q(fecha_fin_publicacion__isnull=True) | Q(fecha_fin_publicacion__gte=today)).select_related("tipo_instalacion")
        for key, field in (("comuna", "comuna_publica__icontains"), ("jornada", "jornada__icontains"), ("turno", "sistema_turno__icontains")):
            if request.query_params.get(key):
                queryset = queryset.filter(**{field: request.query_params[key]})
        return Response(VacantePublicaSerializer(queryset, many=True).data)

    @action(detail=True, methods=["put"], url_path="preferencias")
    def preferencias(self, request, pk=None):
        postulacion = self._get_postulacion(request, pk, editable=True)
        seleccion = request.data.get("vacantes", [])
        if not isinstance(seleccion, list) or not 1 <= len(seleccion) <= 3:
            raise ValidationError({"vacantes": "Selecciona entre una y tres preferencias."})
        ids = [item.get("public_id") for item in seleccion]
        if len(ids) != len(set(ids)):
            raise ValidationError({"vacantes": "No puedes repetir una vacante."})
        disponibles = {
            str(v.public_id): v for v in VacanteGuardia.objects.filter(
                public_id__in=ids, estado="publicado", permite_postulaciones=True,
            ) if v.disponibles > 0
        }
        if len(disponibles) != len(ids):
            raise ValidationError({"vacantes": "Una de las vacantes ya no está disponible."})
        with transaction.atomic():
            postulacion.preferencias.all().delete()
            for index, item in enumerate(seleccion, start=1):
                PreferenciaVacantePostulante.objects.create(
                    postulacion=postulacion,
                    vacante=disponibles[str(item["public_id"])],
                    orden_preferencia=item.get("orden_preferencia", index),
                )
        return Response(PostulacionPublicaSerializer(postulacion).data)

    @action(detail=True, methods=["post", "get"], url_path="evaluacion")
    def evaluacion(self, request, pk=None):
        postulacion = self._get_postulacion(request, pk, editable=request.method == "POST")
        evaluacion, created = EvaluacionPostulacion.objects.get_or_create(postulacion=postulacion)
        if created:
            tipos = list(
                TipoInstalacionLaboral.objects.filter(vacantes__interesados__postulacion=postulacion)
                .distinct()
            )
            generales = list(PreguntaPostulacion.objects.filter(activo=True, tipo_instalacion__slug="general").order_by("orden", "id")[:3])
            seleccionadas = list(generales)
            for tipo in tipos:
                candidatas = list(PreguntaPostulacion.objects.filter(activo=True, tipo_instalacion=tipo).exclude(id__in=[p.id for p in seleccionadas]).order_by("orden", "id")[:3])
                seleccionadas.extend(candidatas)
            seleccionadas = seleccionadas[: getattr(settings, "POSTULACIONES_MAX_PREGUNTAS", 10)]
            for index, pregunta in enumerate(seleccionadas, start=1):
                PreguntaAsignadaEvaluacion.objects.create(
                    evaluacion=evaluacion, pregunta_origen=pregunta, texto=pregunta.texto,
                    tipo_respuesta=pregunta.tipo_respuesta, opciones=pregunta.opciones,
                    respuesta_correcta=pregunta.respuesta_correcta, puntaje=pregunta.puntaje,
                    obligatoria=pregunta.obligatoria,
                    tipo_instalacion_nombre=pregunta.tipo_instalacion.nombre if pregunta.tipo_instalacion else "General",
                    orden=index,
                )
            postulacion.estado = "evaluacion_pendiente"
            postulacion.save(update_fields=("estado", "actualizado_en"))
        preguntas = evaluacion.preguntas_asignadas.all()
        return Response({"id": evaluacion.id, "finalizada_en": evaluacion.finalizada_en, "preguntas": PreguntaPublicaSerializer(preguntas, many=True).data})

    @action(detail=True, methods=["put"], url_path="respuestas")
    def respuestas(self, request, pk=None):
        postulacion = self._get_postulacion(request, pk, editable=True)
        try:
            evaluacion = postulacion.evaluacion
        except EvaluacionPostulacion.DoesNotExist:
            raise ValidationError({"detail": "Primero debes iniciar la evaluación."})
        if evaluacion.finalizada_en:
            raise ValidationError({"detail": "La evaluación ya fue finalizada."})
        respuestas = request.data.get("respuestas", [])
        asignadas = {item.id: item for item in evaluacion.preguntas_asignadas.all()}
        for item in respuestas:
            pregunta = asignadas.get(item.get("pregunta"))
            if not pregunta:
                raise ValidationError({"respuestas": "Intentaste responder una pregunta no asignada."})
            RespuestaPostulacion.objects.update_or_create(
                pregunta_asignada=pregunta, defaults={"respuesta": item.get("respuesta")}
            )
        return Response(PreguntaPublicaSerializer(evaluacion.preguntas_asignadas.all(), many=True).data)

    @action(detail=True, methods=["post"], url_path="documentos")
    def documentos(self, request, pk=None):
        postulacion = self._get_postulacion(request, pk, editable=True)
        archivo = request.FILES.get("archivo")
        tipo = str(request.data.get("tipo_documento", "")).strip()
        if not archivo or not tipo:
            raise ValidationError({"archivo": "Adjunta un archivo e indica su tipo."})
        max_size = getattr(settings, "POSTULACIONES_DOCUMENT_MAX_SIZE", 10 * 1024 * 1024)
        if archivo.size > max_size:
            raise ValidationError({"archivo": "El archivo supera el tamaño máximo permitido."})
        mime = getattr(archivo, "content_type", "")
        signature = archivo.read(12)
        archivo.seek(0)
        if mime not in ALLOWED_MIME or not any(signature.startswith(prefix) for prefix in ALLOWED_MIME[mime]):
            raise ValidationError({"archivo": "Solo se permiten PDF, JPG y PNG válidos."})
        extension = {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png"}[mime]
        key = f"postulaciones/{postulacion.id_publico}/{uuid.uuid4().hex}.{extension}"
        try:
            upload_document(archivo, key)
            documento = DocumentoPostulacion.objects.create(
                postulacion=postulacion, tipo_documento=tipo,
                nombre_original=archivo.name[:255], storage_key=key,
                mime_type=mime, size=archivo.size,
            )
        except Exception:
            try:
                delete_document(key)
            except Exception:
                pass
            raise
        audit(postulacion, "documento_cargado", request, {"tipo": tipo})
        return Response(DocumentoPublicoSerializer(documento).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["delete"], url_path=r"documentos/(?P<documento_id>\d+)")
    def eliminar_documento(self, request, pk=None, documento_id=None):
        postulacion = self._get_postulacion(request, pk, editable=True)
        try:
            documento = postulacion.documentos.get(pk=documento_id)
        except DocumentoPostulacion.DoesNotExist:
            raise NotFound("Documento no encontrado.")
        delete_document(documento.storage_key)
        documento.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"], url_path="resumen")
    def resumen(self, request, pk=None):
        postulacion = self._get_postulacion(request, pk)
        return Response(PostulacionPublicaSerializer(postulacion).data)

    @action(detail=True, methods=["post"], url_path="finalizar")
    def finalizar(self, request, pk=None):
        postulacion = self._get_postulacion(request, pk, editable=True)
        errores = {}
        if len(postulacion.presentacion.strip()) < 40:
            errores["presentacion"] = "Completa tu presentación personal."
        if not postulacion.preferencias.exists():
            errores["preferencias"] = "Selecciona al menos una vacante."
        try:
            pendientes = postulacion.evaluacion.preguntas_asignadas.filter(
                obligatoria=True, respuesta__isnull=True
            ).exists()
        except EvaluacionPostulacion.DoesNotExist:
            pendientes = True
        if pendientes:
            errores["evaluacion"] = "Responde todas las preguntas obligatorias."
        if not request.data.get("declaracion_veracidad") or not request.data.get("consentimiento_datos"):
            errores["consentimiento"] = "Debes aceptar la declaración y el tratamiento de datos."
        if errores:
            raise ValidationError(errores)
        now = timezone.now()
        postulacion.estado = "finalizada"
        postulacion.finalizada_en = now
        postulacion.declaracion_veracidad = True
        postulacion.consentimiento_datos = True
        postulacion.version_consentimiento = getattr(settings, "POSTULACIONES_CONSENT_VERSION", "2026-01")
        postulacion.consentimiento_en = now
        postulacion.save()
        postulacion.evaluacion.finalizada_en = now
        postulacion.evaluacion.save(update_fields=("finalizada_en",))
        qr, _ = TokenQrPostulacion.objects.get_or_create(postulacion=postulacion)
        audit(postulacion, "postulacion_finalizada", request)
        base = getattr(settings, "POSTULACIONES_ADMIN_URL", "https://admin.inout.cl").rstrip("/")
        return Response({"codigo": postulacion.codigo, "qr_url": f"{base}/postulaciones/verificar/{qr.token}"})


class AdminPostulacionViewSet(viewsets.ModelViewSet):
    permission_classes = [IsPostulacionesAdmin]
    queryset = PostulacionGuardia.objects.all().prefetch_related(
        "estudios", "cursos", "experiencias", "preferencias__vacante__instalacion",
        "documentos",
    )
    http_method_names = ["get", "patch", "head", "options"]

    def get_serializer_class(self):
        return PostulacionAdminDetalleSerializer if self.action in ("retrieve", "partial_update", "verificar_qr") else PostulacionAdminListSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(nombres__icontains=search) | Q(apellido_paterno__icontains=search)
                | Q(rut__icontains=search) | Q(codigo__icontains=search)
            )
        for param, field in (("estado", "estado"), ("comuna", "comuna_residencia__icontains"), ("os10", "estado_os10")):
            value = self.request.query_params.get(param)
            if value:
                queryset = queryset.filter(**{field: value})
        return queryset

    def partial_update(self, request, *args, **kwargs):
        postulacion = self.get_object()
        old = postulacion.estado
        response = super().partial_update(request, *args, **kwargs)
        if old != postulacion.estado:
            audit(postulacion, "cambio_estado", request, {"desde": old, "hasta": postulacion.estado})
        return response

    @action(detail=False, methods=["get"], url_path=r"verificar-qr/(?P<token>[^/.]+)")
    def verificar_qr(self, request, token=None):
        try:
            qr = TokenQrPostulacion.objects.select_related("postulacion").get(token=token, activo=True)
        except TokenQrPostulacion.DoesNotExist:
            raise NotFound("QR inválido o revocado.")
        qr.ultimo_uso = timezone.now()
        qr.save(update_fields=("ultimo_uso",))
        audit(qr.postulacion, "consulta_qr", request)
        return Response(PostulacionAdminDetalleSerializer(qr.postulacion).data)

    @action(detail=True, methods=["post"], url_path="observaciones")
    def observaciones(self, request, pk=None):
        postulacion = self.get_object()
        serializer = ObservacionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(postulacion=postulacion, autor=request.user)
        audit(postulacion, "observacion_agregada", request)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="entrevistas")
    def entrevistas(self, request, pk=None):
        postulacion = self.get_object()
        serializer = EntrevistaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(postulacion=postulacion)
        audit(postulacion, "entrevista_programada", request)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path=r"documentos/(?P<documento_id>\d+)/validar")
    def validar_documento(self, request, pk=None, documento_id=None):
        postulacion = self.get_object()
        try:
            documento = postulacion.documentos.get(pk=documento_id)
        except DocumentoPostulacion.DoesNotExist:
            raise NotFound("Documento no encontrado.")
        nuevo_estado = request.data.get("estado")
        if nuevo_estado not in ("validado", "rechazado"):
            raise ValidationError({"estado": "Usa validado o rechazado."})
        documento.estado = nuevo_estado
        documento.observaciones = request.data.get("observaciones", "")
        documento.validado_por = request.user
        documento.validado_en = timezone.now()
        documento.save()
        audit(postulacion, f"documento_{nuevo_estado}", request, {"documento": documento.id})
        return Response(DocumentoAdminSerializer(documento).data)

    @action(detail=True, methods=["post"], url_path="rotar-qr")
    def rotar_qr(self, request, pk=None):
        postulacion = self.get_object()
        TokenQrPostulacion.objects.filter(postulacion=postulacion).delete()
        qr = TokenQrPostulacion.objects.create(postulacion=postulacion)
        audit(postulacion, "qr_rotado", request)
        base = getattr(settings, "POSTULACIONES_ADMIN_URL", "https://admin.inout.cl").rstrip("/")
        return Response({"qr_url": f"{base}/postulaciones/verificar/{qr.token}"})

    @action(detail=False, methods=["get"], url_path="dashboard")
    def dashboard(self, request):
        queryset = PostulacionGuardia.objects.all()
        return Response({
            "total": queryset.count(),
            "por_estado": list(queryset.values("estado").annotate(total=Count("id")).order_by("estado")),
            "os10_vigente": queryset.filter(estado_os10="vigente").count(),
            "sin_os10": queryset.filter(estado_os10="no_tiene").count(),
            "por_comuna": list(queryset.values("comuna_residencia").annotate(total=Count("id")).order_by("-total")[:10]),
            "vacantes_interes": list(
                VacanteGuardia.objects.values("public_id", "descripcion_publica")
                .annotate(total=Count("interesados")).order_by("-total")[:10]
            ),
        })


class VacanteAdminViewSet(viewsets.ModelViewSet):
    permission_classes = [IsPostulacionesAdmin]
    queryset = VacanteGuardia.objects.select_related("instalacion", "tipo_instalacion")
    serializer_class = VacanteAdminSerializer


class PreguntaAdminViewSet(viewsets.ModelViewSet):
    permission_classes = [IsPostulacionesAdmin]
    queryset = PreguntaPostulacion.objects.select_related("tipo_instalacion")
    serializer_class = PreguntaAdminSerializer


class TipoInstalacionAdminViewSet(viewsets.ModelViewSet):
    permission_classes = [IsPostulacionesAdmin]
    queryset = TipoInstalacionLaboral.objects.all()
    serializer_class = TipoInstalacionSerializer
