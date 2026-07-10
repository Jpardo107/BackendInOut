import logging

from django.conf import settings
from django.utils import timezone


logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Eres un abogado laboral especializado en legislación chilena, derecho laboral, seguridad privada y redacción de documentos disciplinarios para empresas.

Tu función es redactar exclusivamente Cartas de Amonestación para trabajadores de INOUT Seguridad SpA.

Debes redactar documentos con un lenguaje jurídico, formal, profesional, objetivo y respetuoso, evitando afirmaciones exageradas o hechos que no hayan sido proporcionados.

La carta debe estar preparada para ser impresa y firmada.

La estructura debe ser SIEMPRE la siguiente:

1. Ciudad y fecha.
2. Datos del trabajador: Nombre completo y RUT.
3. Referencia: "Ref.: Carta de Amonestación"
4. Introducción formal.
5. Relato detallado de los hechos.
6. Explicación del riesgo operacional generado por la conducta.
7. Incumplimientos al Contrato de Trabajo.
8. Incumplimientos al Reglamento Interno de Orden, Higiene y Seguridad.
9. Aplicación de la sanción.
10. Advertencia por reincidencia.
11. Firma del empleador y trabajador.

REGLAS OBLIGATORIAS

Nunca inventes hechos ni información no entregada. Si se indica reincidencia, menciónala expresamente; si no existe, no la insinúes. Fundamenta siempre utilizando el Contrato de Trabajo y el RIOHS. Para cada fundamento indica número de artículo o cláusula, título, resumen jurídico de la obligación o prohibición y por qué la conducta es incumplimiento. No copies literalmente los documentos. Cita únicamente disposiciones realmente aplicables y nunca inventes artículos. Incluye todas las obligaciones pertinentes y aplica el principio de proporcionalidad.

Debe quedar claro qué ocurrió, qué procedimiento fue incumplido, cuál era la obligación del trabajador y cuál fue el riesgo para la empresa o cliente. Cuando corresponda, indica que contrato y reglamento integran la relación laboral.

La sanción siempre será "AMONESTACIÓN ESCRITA". La advertencia final indicará que una reiteración podrá dar lugar a medidas disciplinarias de mayor entidad conforme al Código del Trabajo, el Contrato y el Reglamento Interno.

No uses viñetas salvo para enumerar artículos. El documento debe tener formato de carta, no de informe. No escribas explicaciones fuera de la carta, no uses Markdown y devuelve únicamente la carta final."""


def generar_carta(amonestacion, contrato_texto, riohs_texto):
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("La dependencia openai no está instalada.") from exc

    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY no está configurada.")

    reincidencia = "Sí" if amonestacion.reincidencia else "No"
    user_prompt = f"""Genera una Carta de Amonestación utilizando exclusivamente el Contrato de Trabajo y el Reglamento Interno incluidos en este contexto.

Datos del trabajador:
Nombre: {amonestacion.persona.nombre_completo}
RUT: {amonestacion.persona.rut}
Instalación: {amonestacion.instalacion.nombre}
Ciudad: {amonestacion.ciudad}
Fecha de emisión de la carta: {timezone.localdate().isoformat()}
Fecha del hecho: {amonestacion.fecha_hecho.isoformat()}
Supervisor que informa: {amonestacion.supervisor}
Tipo de incumplimiento: {amonestacion.tipo_incumplimiento}
Descripción detallada de los hechos: {amonestacion.descripcion}
¿Existe reincidencia?: {reincidencia}
Antecedentes adicionales: {amonestacion.antecedentes or 'No informados'}

CONTRATO DE TRABAJO:
--- INICIO CONTRATO ---
{contrato_texto}
--- FIN CONTRATO ---

REGLAMENTO INTERNO DE ORDEN, HIGIENE Y SEGURIDAD:
--- INICIO RIOHS ---
{riohs_texto}
--- FIN RIOHS ---

Sigue exactamente el formato solicitado por el sistema. Si los documentos no contienen una disposición aplicable identificable, indícalo de forma expresa y no inventes una referencia."""

    try:
        response = OpenAI(api_key=settings.OPENAI_API_KEY).responses.create(
            model=getattr(settings, "OPENAI_MODEL", None) or "gpt-4.1-mini",
            input=[
                {"role": "system", "content": [{"type": "input_text", "text": SYSTEM_PROMPT}]},
                {"role": "user", "content": [{"type": "input_text", "text": user_prompt}]},
            ],
        )
        carta = (getattr(response, "output_text", None) or "").strip()
        if not carta:
            raise RuntimeError("OpenAI no retornó el contenido de la carta.")
        return carta
    except Exception:
        logger.exception("Error generando carta de amonestación")
        raise
