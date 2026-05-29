import json
import logging
import os
import threading

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import close_old_connections, transaction
from django.db.models import Count
from django.utils.dateparse import parse_date
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from documentacion.services.r2_storage import upload_document

from .models import (
    ImagenReporteInforme,
    ReporteInforme,
    reporte_archivo_origen_upload_key,
    reporte_imagen_upload_key,
)
from .serializers import (
    ReporteIAResultSerializer,
    ReporteInformeCreateSerializer,
    ReporteInformeDetailSerializer,
    ReporteInformeListSerializer,
)
from .services.openai_reportes_service import generar_analisis_vulnerabilidades
from .services.report_file_extraction import extract_text_from_report_file, validate_report_file


STANDARD_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
HEIC_IMAGE_EXTENSIONS = {".heic", ".heif"}
ALLOWED_IMAGE_EXTENSIONS = STANDARD_IMAGE_EXTENSIONS | HEIC_IMAGE_EXTENSIONS
ALLOWED_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}


logger = logging.getLogger(__name__)


def user_can_access_instalacion(user, instalacion) -> bool:
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return True
    return True


def _first(data, *keys, default=""):
    for key in keys:
        value = _get_first_value(data, key, default=None)
        if value not in (None, ""):
            return value
    return default


def _get_first_value(data, key, default=""):
    if not hasattr(data, "get"):
        return default

    value = data.get(key, default)
    if isinstance(value, list):
        return value[0] if value else default
    return value if value is not None else default


def _get_list(data, *keys):
    for key in keys:
        if hasattr(data, "getlist"):
            values = data.getlist(key)
            if values:
                return values
        value = data.get(key)
        if isinstance(value, list):
            return value
    return []


def _indexed_value(data, names, index, fallback_values=None):
    for name in names:
        for key in (f"{name}[{index}]", f"{name}.{index}"):
            value = data.get(key)
            if value not in (None, ""):
                return value

    if fallback_values and index < len(fallback_values):
        return fallback_values[index]
    return ""


def _parse_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "si", "yes", "on"}


def _normalize_instalacion(value):
    if isinstance(value, dict):
        return value.get("id") or value.get("value")
    return value


def _normalize_payload(request):
    data = request.data
    personal_policial = data.get("personalPolicial") if isinstance(data.get("personalPolicial"), dict) else {}

    normalized = {
        "tipo_reporte": _first(data, "tipo_reporte", "tipoReporte"),
        "instalacion": _normalize_instalacion(
            _first(data, "instalacion", "instalacionId", "instalacionSeleccionada")
        ),
        "zona": _first(data, "zona", "zonaSeleccionada"),
        "descripcion_hechos": _first(data, "descripcion_hechos", "descripcionHechos"),
        "analisis_final_usuario": _first(data, "analisis_final_usuario", "recomendaciones"),
        "personal_presente": _first(data, "personal_presente", "personalPresente"),
        "personal_policial_presente": _parse_bool(
            _first(data, "personal_policial_presente", "personalPolicialPresente", default=False)
        ),
        "carabinero_cargo": (
            _first(
                data,
                "carabinero_cargo",
                "personalPolicial.carabinero",
                "personalPolicial[carabinero]",
            )
            or personal_policial.get("carabinero", "")
        ),
        "patente_patrulla": (
            _first(
                data,
                "patente_patrulla",
                "personalPolicial.patente",
                "personalPolicial[patente]",
            )
            or personal_policial.get("patente", "")
        ),
        "numero_carro_policial": (
            _first(
                data,
                "numero_carro_policial",
                "personalPolicial.carro",
                "personalPolicial[carro]",
            )
            or personal_policial.get("carro", "")
        ),
        "fecha_emision": _first(data, "fecha_emision", "fechaEmision", "fecha"),
    }

    autor_nombre = _first(data, "autor_nombre", "autorInforme")
    autor_cargo = _first(data, "autor_cargo", "cargoInforme")
    if autor_nombre:
        normalized["autor_nombre"] = autor_nombre
    if autor_cargo:
        normalized["autor_cargo"] = autor_cargo

    return {key: value for key, value in normalized.items() if value not in (None, "")}


def _coerce_text_list(value):
    if value in (None, ""):
        return []
    if isinstance(value, (list, tuple)):
        if len(value) == 1 and isinstance(value[0], str):
            stripped = value[0].strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                try:
                    parsed = json.loads(stripped)
                except (TypeError, ValueError):
                    pass
                else:
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed]
        return [str(item).strip() for item in value]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
        except (TypeError, ValueError):
            return [stripped]
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed]
        return [stripped]
    return [str(value).strip()]


def _image_text_values(data, names, count):
    if isinstance(names, str):
        names = (names,)

    for name in names:
        for key in (name, f"{name}[]"):
            if hasattr(data, "getlist"):
                values = _coerce_text_list(data.getlist(key))
                if values:
                    return values

            if hasattr(data, "get"):
                values = _coerce_text_list(data.get(key))
                if values:
                    return values

    values = []
    for index in range(count):
        values.append(_indexed_value(data, names, index))
    return values


def _image_text_value(values, index):
    if index < len(values):
        return values[index]
    return ""


def _get_uploaded_images(request):
    files = []
    for key in ("fotos", "fotos[]", "imagenes", "imagenes[]"):
        files.extend(request.FILES.getlist(key))
    return files


def _get_uploaded_report_file(request):
    for key in ("archivo", "file", "informe", "reporte"):
        uploaded = request.FILES.get(key)
        if uploaded:
            return uploaded
    return None


def _validate_images(files):
    max_size = getattr(settings, "REPORTES_IMAGE_MAX_SIZE", 10 * 1024 * 1024)
    for file in files:
        _, ext = os.path.splitext(getattr(file, "name", "") or "")
        ext = ext.lower()
        content_type = getattr(file, "content_type", "")

        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            raise ValidationError({"fotos": f"Extension no permitida para {file.name}."})

        if content_type and content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
            raise ValidationError({"fotos": f"Tipo de imagen no permitido para {file.name}."})

        if getattr(file, "size", 0) > max_size:
            raise ValidationError({"fotos": f"La imagen {file.name} supera el tamano maximo permitido."})


def _is_heic_image(file):
    _, ext = os.path.splitext(getattr(file, "name", "") or "")
    return ext.lower() in HEIC_IMAGE_EXTENSIONS or getattr(file, "content_type", "") in {"image/heic", "image/heif"}


def _prepare_image_for_storage(file):
    if not _is_heic_image(file):
        return file, getattr(file, "name", "") or "", getattr(file, "content_type", "") or ""

    try:
        from PIL import Image
        from pillow_heif import register_heif_opener
    except ImportError as exc:
        raise ValidationError(
            {"fotos": "El servidor no tiene soporte para convertir imagenes HEIC/HEIF."}
        ) from exc

    try:
        register_heif_opener()
        file.seek(0)
        image = Image.open(file)
        image.load()

        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")

        base_name = os.path.splitext(os.path.basename(getattr(file, "name", "") or "imagen"))[0]
        converted_name = f"{base_name or 'imagen'}.jpg"

        buffer = ContentFile(b"", name=converted_name)
        image.save(buffer, format="JPEG", quality=90, optimize=True)
        buffer.seek(0)
        buffer.content_type = "image/jpeg"
        return buffer, converted_name, "image/jpeg"
    except Exception as exc:
        raise ValidationError({"fotos": f"No se pudo convertir la imagen HEIC/HEIF {file.name}."}) from exc


def _apply_ai_result(reporte, result):
    data = result.get("data", {})
    reporte.criticidad_general = data.get("criticidad_general", "")
    reporte.resumen_ejecutivo = data.get("resumen_ejecutivo", "")
    reporte.conclusion_profesional = data.get("conclusion_profesional", "")
    reporte.riesgos_detectados = data.get("riesgos_detectados", [])
    reporte.recomendaciones_ia = data.get("recomendaciones", [])
    reporte.matriz_riesgo = data.get("matriz_riesgo", [])
    reporte.texto_final_pdf = data.get("texto_final_pdf", "")
    reporte.respuesta_ia_raw = result.get("raw") or data
    reporte.estado = ReporteInforme.ESTADO_GENERADO
    reporte.save(
        update_fields=[
            "criticidad_general",
            "resumen_ejecutivo",
            "conclusion_profesional",
            "riesgos_detectados",
            "recomendaciones_ia",
            "matriz_riesgo",
            "texto_final_pdf",
            "respuesta_ia_raw",
            "estado",
            "actualizado_en",
        ]
    )


def _safe_error(exc):
    return str(exc)[:500] or exc.__class__.__name__


def _error_response(detail, source, exc, status_code):
    return Response(
        {
            "detail": detail,
            "source": source,
            "error": _safe_error(exc),
        },
        status=status_code,
    )


def _run_vulnerabilidades_ai(reporte):
    try:
        result = generar_analisis_vulnerabilidades(
            ReporteInforme.objects.prefetch_related("imagenes").get(id=reporte.id)
        )
        _apply_ai_result(reporte, result)
    except Exception as exc:
        logger.exception("Error IA reporte")
        reporte.estado = ReporteInforme.ESTADO_ERROR_IA
        reporte.respuesta_ia_raw = {"error": _safe_error(exc)}
        reporte.save(update_fields=["estado", "respuesta_ia_raw", "actualizado_en"])


def _run_vulnerabilidades_ai_by_id(reporte_id):
    close_old_connections()
    try:
        reporte = ReporteInforme.objects.get(id=reporte_id)
        _run_vulnerabilidades_ai(reporte)
    finally:
        close_old_connections()


def _schedule_vulnerabilidades_ai(reporte):
    reporte.estado = ReporteInforme.ESTADO_PROCESANDO_IA
    reporte.save(update_fields=["estado", "actualizado_en"])

    thread = threading.Thread(
        target=_run_vulnerabilidades_ai_by_id,
        args=(reporte.id,),
        daemon=True,
    )
    transaction.on_commit(thread.start)


class ReporteInformeViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        queryset = (
            ReporteInforme.objects.select_related("instalacion", "usuario_creador")
            .prefetch_related("imagenes")
            .annotate(cantidad_imagenes=Count("imagenes"))
        )

        tipo_reporte = self.request.query_params.get("tipo_reporte") or self.request.query_params.get("tipoReporte")
        instalacion = self.request.query_params.get("instalacion")
        estado = self.request.query_params.get("estado")
        fecha = self.request.query_params.get("fecha")
        fecha_desde = self.request.query_params.get("fecha_desde")
        fecha_hasta = self.request.query_params.get("fecha_hasta")

        if tipo_reporte:
            tipo_reporte = tipo_reporte.replace("-", "_")
            if tipo_reporte == "reporte_vulnerabilidades":
                tipo_reporte = ReporteInforme.TIPO_VULNERABILIDADES
            queryset = queryset.filter(tipo_reporte=tipo_reporte)
        if instalacion:
            queryset = queryset.filter(instalacion_id=instalacion)
        if estado:
            queryset = queryset.filter(estado=estado)
        if fecha:
            parsed = parse_date(fecha)
            if parsed:
                queryset = queryset.filter(fecha_emision=parsed)
        if fecha_desde:
            parsed = parse_date(fecha_desde)
            if parsed:
                queryset = queryset.filter(fecha_emision__gte=parsed)
        if fecha_hasta:
            parsed = parse_date(fecha_hasta)
            if parsed:
                queryset = queryset.filter(fecha_emision__lte=parsed)

        return queryset

    def get_serializer_class(self):
        if self.action == "list":
            return ReporteInformeListSerializer
        if self.action == "create":
            return ReporteInformeCreateSerializer
        if self.action == "generar_ia":
            return ReporteIAResultSerializer
        return ReporteInformeDetailSerializer

    def perform_create(self, serializer):
        raise NotImplementedError

    def create(self, request, *args, **kwargs):
        logger.info("Creando reporte informe")

        try:
            payload = _normalize_payload(request)
            files = _get_uploaded_images(request)
            _validate_images(files)
        except ValidationError:
            logger.exception("Error validando payload reporte informe")
            raise
        except Exception as exc:
            logger.exception("Error creando reporte informe")
            return _error_response(
                "No se pudo procesar la solicitud del reporte",
                "payload",
                exc,
                status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(data=payload, context={"request": request})
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as exc:
            logger.exception("Error validando serializer reporte informe")
            return Response(
                {
                    "detail": "Datos invalidos para crear reporte",
                    "source": "serializer",
                    "error": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        instalacion = serializer.validated_data["instalacion"]
        if not user_can_access_instalacion(request.user, instalacion):
            raise PermissionDenied("No tienes acceso a esta instalacion.")

        try:
            reporte = ReporteInforme.objects.create(
                usuario_creador=request.user,
                estado=ReporteInforme.ESTADO_BORRADOR,
                **serializer.validated_data,
            )
        except Exception as exc:
            logger.exception("Error creando reporte informe")
            return _error_response(
                "No se pudo crear el reporte",
                "db_create",
                exc,
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        descripciones = _image_text_values(
            request.data,
            (
                "descripciones",
                "descripcionFoto",
                "descripcionFotos",
                "descripcionesFoto",
                "fotoDescripcion",
                "fotoDescripciones",
            ),
            len(files),
        )
        recomendaciones = _image_text_values(
            request.data,
            (
                "recomendacionesFoto",
                "recomendacionFoto",
                "recomendacionesFotos",
                "fotoRecomendacion",
                "fotoRecomendaciones",
            ),
            len(files),
        )

        for index, file in enumerate(files):
            try:
                storage_file, stored_name, stored_content_type = _prepare_image_for_storage(file)
                key = reporte_imagen_upload_key(reporte.id, stored_name)
            except ValidationError:
                reporte.delete()
                logger.exception("Error validando imagen reporte")
                raise
            except Exception as exc:
                reporte.delete()
                logger.exception("Error preparando imagen reporte")
                return _error_response(
                    "No se pudo preparar imagen del reporte",
                    "image_prepare",
                    exc,
                    status.HTTP_400_BAD_REQUEST,
                )

            try:
                upload_document(file=storage_file, key=key)
            except Exception as exc:
                reporte.delete()
                logger.exception("Error subiendo imagen reporte a R2")
                return _error_response(
                    "No se pudo subir imagen a Cloudflare R2",
                    "r2_upload",
                    exc,
                    status.HTTP_502_BAD_GATEWAY,
                )

            try:
                ImagenReporteInforme.objects.create(
                    reporte=reporte,
                    storage_key=key,
                    nombre_original=stored_name,
                    mime_type=stored_content_type,
                    size=getattr(storage_file, "size", 0) or 0,
                    descripcion=_image_text_value(descripciones, index),
                    recomendacion_usuario=_image_text_value(recomendaciones, index),
                    orden=index,
                )
            except Exception as exc:
                reporte.delete()
                logger.exception("Error creando imagen reporte informe")
                return _error_response(
                    "No se pudo registrar imagen del reporte",
                    "image_db_create",
                    exc,
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        if reporte.tipo_reporte == ReporteInforme.TIPO_VULNERABILIDADES:
            _schedule_vulnerabilidades_ai(reporte)

        try:
            detail = ReporteInformeDetailSerializer(reporte, context={"request": request})
            return Response(detail.data, status=status.HTTP_201_CREATED)
        except Exception as exc:
            logger.exception("Error creando reporte informe")
            return _error_response(
                "Reporte creado, pero no se pudo serializar la respuesta",
                "response_serialization",
                exc,
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["post"], url_path="importar")
    def importar(self, request):
        report_file = _get_uploaded_report_file(request)
        if not report_file:
            raise ValidationError({"archivo": "Debes subir un informe en PDF, DOCX o TXT."})

        max_size = getattr(settings, "REPORTES_IMPORT_MAX_SIZE", 20 * 1024 * 1024)
        validate_report_file(report_file, max_size)
        extracted_text = extract_text_from_report_file(report_file)
        if not extracted_text:
            raise ValidationError({"archivo": "No se pudo extraer texto del informe subido."})

        payload = _normalize_payload(request)
        payload.setdefault("tipo_reporte", ReporteInforme.TIPO_VULNERABILIDADES)
        payload.setdefault("descripcion_hechos", extracted_text)
        payload.setdefault("analisis_final_usuario", _first(request.data, "analisis_final_usuario", "recomendaciones"))

        serializer = ReporteInformeCreateSerializer(data=payload, context={"request": request})
        serializer.is_valid(raise_exception=True)

        instalacion = serializer.validated_data["instalacion"]
        if not user_can_access_instalacion(request.user, instalacion):
            raise PermissionDenied("No tienes acceso a esta instalacion.")

        with transaction.atomic():
            reporte = ReporteInforme.objects.create(
                usuario_creador=request.user,
                estado=ReporteInforme.ESTADO_BORRADOR,
                texto_extraido_origen=extracted_text,
                **serializer.validated_data,
            )
            key = reporte_archivo_origen_upload_key(reporte.id, getattr(report_file, "name", ""))
            report_file.seek(0)
            upload_document(file=report_file, key=key)
            reporte.archivo_origen_storage_key = key
            reporte.archivo_origen_nombre = getattr(report_file, "name", "") or ""
            reporte.archivo_origen_mime_type = getattr(report_file, "content_type", "") or ""
            reporte.archivo_origen_size = getattr(report_file, "size", 0) or 0
            reporte.save(
                update_fields=[
                    "archivo_origen_storage_key",
                    "archivo_origen_nombre",
                    "archivo_origen_mime_type",
                    "archivo_origen_size",
                    "actualizado_en",
                ]
            )

        if reporte.tipo_reporte == ReporteInforme.TIPO_VULNERABILIDADES:
            _schedule_vulnerabilidades_ai(reporte)

        detail = ReporteInformeDetailSerializer(reporte, context={"request": request})
        return Response(detail.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="generar-ia")
    def generar_ia(self, request, pk=None):
        reporte = self.get_object()
        if not user_can_access_instalacion(request.user, reporte.instalacion):
            raise PermissionDenied("No tienes acceso a esta instalacion.")

        if reporte.tipo_reporte != ReporteInforme.TIPO_VULNERABILIDADES:
            raise ValidationError({"tipo_reporte": "La IA esta habilitada solo para vulnerabilidades por ahora."})

        if reporte.estado == ReporteInforme.ESTADO_GENERADO:
            return Response(ReporteIAResultSerializer(reporte, context={"request": request}).data)

        if reporte.estado != ReporteInforme.ESTADO_PROCESANDO_IA:
            _schedule_vulnerabilidades_ai(reporte)

        return Response(
            ReporteIAResultSerializer(reporte, context={"request": request}).data,
            status=status.HTTP_202_ACCEPTED,
        )
