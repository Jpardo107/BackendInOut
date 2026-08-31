import logging

from django.conf import settings
from django.core.mail import EmailMessage

from postulaciones.models import DestinatariosPostulacionZona
from .ficha_pdf import generar_ficha_postulante_pdf

logger = logging.getLogger(__name__)


def destinatarios_para_postulacion(postulacion):
    zonas = list(
        postulacion.preferencias.values_list("vacante__instalacion__zona", flat=True).distinct()
    )
    configuraciones = DestinatariosPostulacionZona.objects.all()
    if zonas:
        configuraciones = configuraciones.filter(zona__codigo__in=zonas)
    return list(dict.fromkeys(
        correo
        for correos in configuraciones.values_list("correos", flat=True)
        for correo in correos
    ))


def enviar_comprobante_postulacion(postulacion):
    destinatarios = destinatarios_para_postulacion(postulacion)
    if not destinatarios:
        logger.warning("Postulación %s finalizada sin destinatarios configurados", postulacion.codigo)
        return 0
    try:
        pdf = generar_ficha_postulante_pdf(postulacion)
        vacantes = list(postulacion.preferencias.values_list("vacante__descripcion_publica", flat=True))
        destino = ", ".join(vacantes) if vacantes else "Banco de postulantes"
        mensaje = EmailMessage(
            subject=f"Nueva postulación {postulacion.codigo} · {postulacion.nombre_completo}",
            body=(
                f"Se recibió una nueva postulación.\n\n"
                f"Postulante: {postulacion.nombre_completo}\n"
                f"Código: {postulacion.codigo}\n"
                f"Destino: {destino}\n\n"
                "Se adjunta la ficha completa en PDF."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=destinatarios,
        )
        mensaje.attach(f"ficha-{postulacion.codigo}.pdf", pdf, "application/pdf")
        return mensaje.send(fail_silently=False)
    except Exception:
        logger.exception("No fue posible enviar el comprobante de la postulación %s", postulacion.codigo)
        return 0
