"""Correo diario (lunes a viernes, 07:00 hora Chile) con las solicitudes registradas en supervisiones."""
import logging
from datetime import datetime, timedelta
from html import escape
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db.models import Q
from django.utils import timezone

from .models import ConfiguracionResumenSolicitudes, EnvioResumenSolicitudes, Supervision

logger = logging.getLogger(__name__)

CHILE_TZ = ZoneInfo("America/Santiago")
HORA_ENVIO = 7
MAX_DESTINATARIOS = 20


def get_configuracion():
    configuracion, _ = ConfiguracionResumenSolicitudes.objects.get_or_create(pk=1)
    return configuracion


def ahora_chile():
    return timezone.now().astimezone(CHILE_TZ)


def ventana_envio(ahora):
    """Últimas 24 horas; el lunes cubre desde el viernes 07:00 para no perder las del fin de semana."""
    horas = 72 if ahora.weekday() == 0 else 24
    return ahora - timedelta(hours=horas), ahora


def _momento_solicitud(supervision):
    if supervision.creada_en:
        return supervision.creada_en.astimezone(CHILE_TZ)
    return datetime.combine(supervision.fecha, supervision.hora_final, tzinfo=CHILE_TZ)


def solicitudes_entre(desde, hasta):
    candidatas = (
        Supervision.objects.select_related("supervisor", "instalacion")
        .exclude(solicitudes__isnull=True)
        .exclude(solicitudes__exact="")
        .filter(
            Q(creada_en__gte=desde, creada_en__lt=hasta)
            | Q(creada_en__isnull=True, fecha__gte=desde.astimezone(CHILE_TZ).date(), fecha__lte=hasta.astimezone(CHILE_TZ).date())
        )
    )
    filas = []
    for supervision in candidatas:
        texto = supervision.solicitudes.strip()
        if not texto or texto.lower() == "sin solicitudes":
            continue
        momento = _momento_solicitud(supervision)
        if not desde <= momento < hasta:
            continue
        supervisor = supervision.supervisor
        filas.append({
            "supervisor": f"{supervisor.nombres} {supervisor.apellidos}".strip() if supervisor else "Sin supervisor",
            "instalacion": supervision.instalacion.nombre,
            "detalle": texto,
            "momento": momento,
        })
    return sorted(filas, key=lambda fila: fila["momento"])


def _formato(momento):
    return momento.astimezone(CHILE_TZ).strftime("%d-%m-%Y %H:%M")


def construir_mensaje(filas, desde, hasta, prueba=False):
    prefijo = "PRUEBA: " if prueba else ""
    asunto = f"{prefijo}Solicitudes de supervisión {hasta.astimezone(CHILE_TZ).strftime('%d-%m-%Y')} ({len(filas)})"
    periodo = f"{_formato(desde)} a {_formato(hasta)}"

    if filas:
        texto = "\n\n".join(
            f"{i}. {fila['supervisor']} — {fila['instalacion']}\n"
            f"   Fecha y hora: {_formato(fila['momento'])}\n"
            f"   Solicitud: {fila['detalle']}"
            for i, fila in enumerate(filas, start=1)
        )
        filas_html = "".join(
            f'<tr><td style="padding:8px;border-bottom:1px solid #e5e7eb;white-space:nowrap">{escape(_formato(fila["momento"]))}</td>'
            f'<td style="padding:8px;border-bottom:1px solid #e5e7eb">{escape(fila["supervisor"])}</td>'
            f'<td style="padding:8px;border-bottom:1px solid #e5e7eb">{escape(fila["instalacion"])}</td>'
            f'<td style="padding:8px;border-bottom:1px solid #e5e7eb;white-space:pre-line">{escape(fila["detalle"])}</td></tr>'
            for fila in filas
        )
        cuerpo_html = (
            '<table style="width:100%;border-collapse:collapse;font-size:14px">'
            '<tr style="background:#eef2f7;text-align:left">'
            '<th style="padding:8px">Fecha y hora</th><th style="padding:8px">Supervisor</th>'
            '<th style="padding:8px">Instalación</th><th style="padding:8px">Solicitud</th></tr>'
            f"{filas_html}</table>"
        )
    else:
        texto = "No se registraron solicitudes en este período."
        cuerpo_html = f"<p>{texto}</p>"

    texto = f"Solicitudes de supervisión INOUT\nPeríodo: {periodo}\nTotal: {len(filas)}\n\n{texto}"
    html = (
        '<div style="font-family:Arial,sans-serif;color:#1f2937;max-width:900px">'
        '<div style="background:#193040;color:white;padding:16px 20px;font-size:18px;font-weight:bold">'
        f"{escape(prefijo)}Solicitudes de supervisión INOUT</div>"
        '<div style="border:1px solid #d9e2ec;padding:20px">'
        f"<p><strong>Período:</strong> {escape(periodo)}<br><strong>Total:</strong> {len(filas)}</p>"
        f"{cuerpo_html}</div></div>"
    )
    return asunto, texto, html


def enviar_resumen(ahora=None, prueba=False):
    """Envía el resumen y registra el intento. Devuelve el EnvioResumenSolicitudes creado."""
    ahora = (ahora or ahora_chile()).astimezone(CHILE_TZ)
    desde, hasta = ventana_envio(ahora)
    configuracion = get_configuracion()
    destinatarios = list(configuracion.destinatarios)
    filas = solicitudes_entre(desde, hasta)
    envio = EnvioResumenSolicitudes.objects.create(
        fecha=ahora.date(), prueba=prueba, desde=desde, hasta=hasta, cantidad=len(filas), destinatarios=destinatarios,
    )
    if not destinatarios:
        envio.error = "No existen destinatarios configurados."
        envio.save(update_fields=["error"])
        return envio

    asunto, texto, html = construir_mensaje(filas, desde, hasta, prueba=prueba)
    try:
        message = EmailMultiAlternatives(
            subject=asunto, body=texto, from_email=settings.INFORMACIONES_FROM_EMAIL, to=destinatarios,
        )
        message.attach_alternative(html, "text/html")
        if message.send(fail_silently=False) != 1:
            raise RuntimeError("El servidor de correo no confirmó el envío.")
        envio.enviado = True
        envio.save(update_fields=["enviado"])
    except Exception as exc:
        logger.exception("No se pudo enviar el resumen de solicitudes")
        envio.error = str(exc)[:1000]
        envio.save(update_fields=["error"])
    return envio


def debe_enviar_programado(ahora):
    """Lunes a viernes a las 07 (hora Chile), una sola vez por día y solo si está activo."""
    if ahora.weekday() > 4 or ahora.hour != HORA_ENVIO:
        return False, "Fuera del horario programado (lunes a viernes, 07:00 hora Chile)."
    if not get_configuracion().activo:
        return False, "El correo diario de solicitudes está desactivado."
    if EnvioResumenSolicitudes.objects.filter(fecha=ahora.date(), prueba=False, enviado=True).exists():
        return False, "El resumen de hoy ya fue enviado."
    return True, ""
