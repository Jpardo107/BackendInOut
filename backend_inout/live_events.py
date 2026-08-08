import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.utils import timezone


logger = logging.getLogger(__name__)

LIVE_EVENT_TYPES = frozenset({
    "supervision.created",
    "supervision.started",
    "supervision.completed",
    "supervision.updated",
    "solicitud.created",
    "solicitud.updated",
    "preinforme.created",
    "preinforme.updated",
    "informe.created",
    "informe.updated",
})


def can_access_live(user):
    """Replica la regla actual del AdminWeb: todo usuario activo salvo Supervisor."""
    if not user or not user.is_authenticated or not user.is_active:
        return False
    if user.is_staff or user.is_superuser:
        return True
    cargo = str(getattr(getattr(user, "cargo", None), "nombre", "") or "").strip().lower()
    return cargo != "supervisor"


def live_scope_id(source=None, user=None):
    """Punto único de extensión para migrar de ámbito global a empresa sin tocar emisores."""
    for candidate in (source, getattr(source, "instalacion", None), user):
        empresa_id = getattr(candidate, "empresa_id", None)
        if empresa_id:
            return f"empresa_{empresa_id}"
    return "global"


def live_group_name(source=None, user=None):
    return f"live_{live_scope_id(source=source, user=user)}"


def _publish_live_event(event_type, data, group):
    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            logger.warning("Evento en vivo omitido: channel layer no configurado")
            return
        async_to_sync(channel_layer.group_send)(
            group,
            {
                "type": "live.event",
                "event": {"type": event_type, "data": data},
            },
        )
    except Exception:
        # El tiempo real nunca debe convertir un commit correcto en un error REST.
        logger.exception("No fue posible publicar evento en vivo %s", event_type)


def schedule_live_event(event_type, data, source=None, user=None):
    if event_type not in LIVE_EVENT_TYPES:
        raise ValueError(f"Tipo de evento en vivo no permitido: {event_type}")
    group = live_group_name(source=source, user=user)
    payload = dict(data)
    transaction.on_commit(lambda: _publish_live_event(event_type, payload, group))


def supervision_summary(supervision):
    supervisor = supervision.supervisor
    return {
        "id": supervision.id,
        "instalacion_id": supervision.instalacion_id,
        "instalacion": supervision.instalacion.nombre,
        "supervisor_id": supervision.supervisor_id,
        "supervisor": (
            f"{supervisor.nombres} {supervisor.apellidos}".strip()
            if supervisor else "Sin supervisor"
        ),
        "fecha": supervision.fecha.isoformat(),
        "hora_inicio": supervision.hora_inicio.isoformat(),
        "hora_final": supervision.hora_final.isoformat(),
        "estado_solicitud": supervision.estado_solicitud,
        "novedades": (supervision.novedades or "Sin novedades")[:300],
        "solicitudes": (supervision.solicitudes or "Sin solicitudes")[:300],
    }


def supervision_started_summary(
    instalacion, supervisor, started_at, latitud=None, longitud=None,
    device_date=None, device_time=None,
):
    return {
        "id": None,
        "instalacion_id": instalacion.id,
        "instalacion": instalacion.nombre,
        "supervisor_id": supervisor.id,
        "supervisor": f"{supervisor.nombres} {supervisor.apellidos}".strip(),
        "fecha": (device_date or started_at.date()).isoformat(),
        "hora_inicio": (device_time or started_at.time()).replace(microsecond=0).isoformat(),
        "estado": "en_curso",
        "latitud": latitud,
        "longitud": longitud,
    }


def solicitud_summary(supervision):
    return {
        "id": supervision.id,
        "supervision_id": supervision.id,
        "instalacion_id": supervision.instalacion_id,
        "instalacion": supervision.instalacion.nombre,
        "solicitud": (supervision.solicitudes or "")[:180],
        "estado": supervision.estado_solicitud,
        "fecha": supervision.fecha.isoformat(),
    }


def report_summary(reporte):
    event_time = timezone.localtime(reporte.actualizado_en)
    return {
        "id": reporte.id,
        "tipo_reporte": reporte.tipo_reporte,
        "instalacion_id": reporte.instalacion_id,
        "instalacion": reporte.instalacion.nombre,
        "autor": reporte.autor_nombre,
        "fecha": reporte.fecha_emision.isoformat(),
        "hora": event_time.time().replace(microsecond=0).isoformat(),
        "estado": reporte.estado,
        "criticidad": reporte.criticidad_general,
    }


def schedule_report_event(reporte, action):
    if reporte.tipo_reporte == "pre_informe":
        # En el flujo actual, guardar el preinforme es su acción de finalización.
        if action != "created":
            return
        event_type = "preinforme.created"
    else:
        # Vulnerabilidades solo está terminado después del procesamiento exitoso.
        if action != "updated" or reporte.estado != "generado":
            return
        event_type = "informe.updated"
    schedule_live_event(event_type, report_summary(reporte), source=reporte)
