from django.urls import reverse
from rest_framework import permissions, viewsets, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_time
from backend_inout.live_events import (
    can_access_live,
    schedule_live_event,
    solicitud_summary,
    supervision_summary,
    supervision_started_summary,
)
from instalacion.models import Instalacion
from .models import EnvioResumenSolicitudes, Supervision, FotoSupervision, SupervisionActiva
from .serializers import (
    ConfiguracionResumenSolicitudesSerializer,
    SupervisionSerializer,
    SupervisionDetailSerializer,
    FotoSupervisionSerializer,
)
from .resumen_solicitudes import enviar_resumen, get_configuracion as get_configuracion_resumen
from inventario.views import user_has_inventory_admin_role
from .storage import photo_response, save_supervision_photo
from reportes.views import _prepare_image_for_storage, _validate_images


def get_mes_anio_from_request(request):
    now = timezone.localdate()
    mes = request.query_params.get("mes", now.month)
    anio = request.query_params.get("anio", now.year)

    try:
        mes = int(mes)
        anio = int(anio)
    except (TypeError, ValueError):
        raise ValidationError({"detail": "Los parametros mes y anio deben ser numericos."})

    if mes < 1 or mes > 12:
        raise ValidationError({"mes": "El mes debe estar entre 1 y 12."})

    if anio < 2000 or anio > now.year + 1:
        raise ValidationError({"anio": "El anio solicitado esta fuera del rango permitido."})

    return mes, anio


def active_supervision_summary(active):
    supervisor = active.supervisor
    return {
        "id": active.id,
        "instalacion_id": active.instalacion_id,
        "instalacion": active.instalacion.nombre,
        "instalacion_detalle": {
            "id": active.instalacion_id,
            "nombre": active.instalacion.nombre,
            "direccion": active.instalacion.direccion,
            "comuna": active.instalacion.comuna,
        },
        "supervisor_id": active.supervisor_id,
        "supervisor": f"{supervisor.nombres} {supervisor.apellidos}".strip(),
        "fecha": active.fecha.isoformat(),
        "hora_inicio": active.hora_inicio.isoformat(),
        "latitud": float(active.latitud) if active.latitud is not None else None,
        "longitud": float(active.longitud) if active.longitud is not None else None,
        "estado": "en_curso",
    }


class SupervisionViewSet(viewsets.ModelViewSet):
    serializer_class = SupervisionSerializer

    def get_queryset(self):
        queryset = Supervision.objects.filter(instalacion__activa=True).select_related('instalacion', 'supervisor').prefetch_related('fotos')

        if getattr(self, "action", None) == "list":
            mes, anio = get_mes_anio_from_request(self.request)
            queryset = queryset.filter(fecha__year=anio, fecha__month=mes)

        return queryset.order_by("-fecha", "-hora_inicio")

    def perform_create(self, serializer):
        # El supervisor es quien inició sesión; no se confía en el id que envía el teléfono.
        supervision = serializer.save(supervisor=self.request.user)
        SupervisionActiva.objects.filter(supervisor_id=supervision.supervisor_id).delete()
        summary = supervision_summary(supervision)
        schedule_live_event("supervision.created", summary, source=supervision)
        schedule_live_event("supervision.completed", summary, source=supervision)
        solicitud = (supervision.solicitudes or "").strip().lower()
        if solicitud and solicitud != "sin solicitudes":
            schedule_live_event(
                "solicitud.created",
                solicitud_summary(supervision),
                source=supervision,
            )

    @action(detail=False, methods=["post"], url_path="iniciar")
    def iniciar(self, request):
        instalacion_id = request.data.get("instalacion")
        if not instalacion_id:
            raise ValidationError({"instalacion": "Este campo es obligatorio."})

        try:
            instalacion = Instalacion.objects.get(pk=instalacion_id, activa=True)
        except (Instalacion.DoesNotExist, TypeError, ValueError):
            raise ValidationError({"instalacion": "La instalación no existe."})

        started_at = timezone.localtime()
        raw_device_date = request.data.get("fecha")
        raw_device_time = request.data.get("hora_inicio")
        device_date = parse_date(str(raw_device_date or ""))
        device_time = parse_time(str(raw_device_time or ""))
        if (raw_device_date or raw_device_time) and (not device_date or not device_time):
            raise ValidationError({"inicio": "La fecha u hora local del dispositivo no es válida."})
        latitud = request.data.get("latitud")
        longitud = request.data.get("longitud")
        try:
            latitud = round(float(latitud), 6) if latitud not in (None, "") else None
            longitud = round(float(longitud), 6) if longitud not in (None, "") else None
        except (TypeError, ValueError):
            raise ValidationError({"ubicacion": "Las coordenadas no son válidas."})
        if latitud is not None and not -90 <= latitud <= 90:
            raise ValidationError({"latitud": "La latitud está fuera de rango."})
        if longitud is not None and not -180 <= longitud <= 180:
            raise ValidationError({"longitud": "La longitud está fuera de rango."})

        summary = supervision_started_summary(
            instalacion,
            request.user,
            started_at,
            latitud=latitud,
            longitud=longitud,
            device_date=device_date,
            device_time=device_time,
        )
        active, _ = SupervisionActiva.objects.update_or_create(
            supervisor=request.user,
            defaults={
                "instalacion": instalacion,
                "fecha": device_date or started_at.date(),
                "hora_inicio": device_time or started_at.time().replace(microsecond=0),
                "latitud": latitud,
                "longitud": longitud,
            },
        )
        summary["id"] = active.id
        schedule_live_event(
            "supervision.started",
            summary,
            source=instalacion,
            user=request.user,
        )
        return Response(summary, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get", "delete"], url_path="activa")
    def activa(self, request):
        if request.method == "DELETE":
            SupervisionActiva.objects.filter(supervisor=request.user).delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        active = (
            SupervisionActiva.objects.select_related("instalacion", "supervisor")
            .filter(supervisor=request.user, instalacion__activa=True)
            .first()
        )
        return Response(active_supervision_summary(active) if active else None)

    @action(detail=False, methods=["get"], url_path="activas")
    def activas(self, request):
        if not can_access_live(request.user):
            return Response({"detail": "No autorizado."}, status=status.HTTP_403_FORBIDDEN)
        active = SupervisionActiva.objects.select_related("instalacion", "supervisor").filter(instalacion__activa=True)
        return Response([active_supervision_summary(item) for item in active])

    def partial_update(self, request, *args, **kwargs):
        """Sobrescribimos PATCH para restringirlo solo a 'estado_solicitud'."""
        # Obtenemos la instancia actual
        instance = self.get_object()
        data = request.data

        # Validamos que solo 'estado_solicitud' esté presente en la solicitud
        if set(data.keys()) != {'estado_solicitud'}:
            return Response(
                {"error": "Solo puedes actualizar el campo 'estado_solicitud'."},
                status=status.HTTP_400_BAD_REQUEST
            )
        # Validamos que el 'estado_solicitud' tenga un valor permitido
        allowed_states = ['gestionado', 'entregado', 'denegado', 'pendiente']
        if data['estado_solicitud'] not in allowed_states:
            return Response(
                {"estado_solicitud": f"Estado no válido. Los valores permitidos son: {', '.join(allowed_states)}."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Actualizamos únicamente el campo 'estado_solicitud'
        instance.estado_solicitud = data['estado_solicitud']
        instance.save()

        summary = supervision_summary(instance)
        schedule_live_event("supervision.updated", summary, source=instance)
        solicitud = (instance.solicitudes or "").strip().lower()
        if solicitud and solicitud != "sin solicitudes":
            schedule_live_event(
                "solicitud.updated",
                solicitud_summary(instance),
                source=instance,
            )

        # Retornamos la instancia actualizada
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class SupervisionDetailViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SupervisionDetailSerializer

    def get_queryset(self):
        queryset = (
            Supervision.objects
            .filter(instalacion__activa=True)
            .select_related("instalacion", "supervisor")
            .prefetch_related(
                "estado_cargos_fijos",
                "estado_documentos",
                "fotos",
                "estado_cargos_fijos__cargo_fijo",
                "estado_documentos__documento",
            )
        )

        params_provided = "mes" in self.request.query_params or "anio" in self.request.query_params
        if getattr(self, "action", None) == "list" or params_provided:
            mes, anio = get_mes_anio_from_request(self.request)
            queryset = queryset.filter(fecha__year=anio, fecha__month=mes)

        return queryset.order_by("-fecha", "-hora_inicio")


class FotoSupervisionViewSet(viewsets.ModelViewSet):
    queryset = FotoSupervision.objects.all()
    serializer_class = FotoSupervisionSerializer


class FotoSupervisionUploadView(APIView):
    """Reemplaza al upload_photo.php del cPanel: recibe files[] y devuelve las URLs públicas."""
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [permissions.IsAuthenticated]
    max_files = 20

    def post(self, request):
        files = request.FILES.getlist("files[]") or request.FILES.getlist("files")
        if not files:
            raise ValidationError({"detail": "Debes adjuntar al menos una foto."})
        if len(files) > self.max_files:
            raise ValidationError({"detail": f"Máximo {self.max_files} fotos por envío."})
        _validate_images(files)

        uploaded = []
        for file in files:
            prepared, name, content_type = _prepare_image_for_storage(file)
            key = save_supervision_photo(prepared, name, content_type)
            url = request.build_absolute_uri(reverse("supervision-foto-publica", kwargs={"key": key}))
            uploaded.append({"ruta": url, "url": url, "key": key})
        return Response({"files": uploaded}, status=status.HTTP_201_CREATED)


class FotoSupervisionPublicView(APIView):
    """Sirve las fotos sin token para que funcionen en <img src>. Las keys son UUID no adivinables."""
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request, key):
        return photo_response(key)


class ConfiguracionResumenSolicitudesView(APIView):
    """GET/PUT destinatarios del correo diario de solicitudes; POST envía una prueba con las últimas solicitudes."""

    def check_permissions(self, request):
        super().check_permissions(request)
        if not user_has_inventory_admin_role(request.user):
            raise PermissionDenied("Solo usuarios administrativos pueden configurar el correo de solicitudes.")

    def _data(self, configuracion):
        data = ConfiguracionResumenSolicitudesSerializer(configuracion).data
        ultimo = EnvioResumenSolicitudes.objects.first()
        data["ultimo_envio"] = (
            {
                "creado_en": ultimo.creado_en,
                "prueba": ultimo.prueba,
                "enviado": ultimo.enviado,
                "cantidad": ultimo.cantidad,
                "destinatarios": ultimo.destinatarios,
                "error": ultimo.error,
            }
            if ultimo else None
        )
        return data

    def get(self, request):
        return Response(self._data(get_configuracion_resumen()))

    def put(self, request):
        configuracion = get_configuracion_resumen()
        serializer = ConfiguracionResumenSolicitudesSerializer(configuracion, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(actualizado_por=request.user)
        return Response(self._data(configuracion))

    patch = put

    def post(self, request):
        if not get_configuracion_resumen().destinatarios:
            raise ValidationError({"detail": "Guarda al menos un correo destinatario antes de realizar la prueba."})
        envio = enviar_resumen(prueba=True)
        if not envio.enviado:
            return Response(
                {"detail": f"No fue posible enviar el correo de prueba: {envio.error[:500]}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"detail": f"Correo de prueba enviado con {envio.cantidad} solicitudes.", "cantidad": envio.cantidad})
