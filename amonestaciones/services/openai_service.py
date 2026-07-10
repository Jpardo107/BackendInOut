import logging
import re
import unicodedata

from django.conf import settings
from django.utils import timezone


logger = logging.getLogger(__name__)

MAX_DOCUMENT_CONTEXT_CHARS = 26000
CHUNK_SIZE = 3500
CHUNK_OVERLAP = 400
STOP_WORDS = {
    "ante", "como", "con", "del", "desde", "donde", "el", "ella", "en", "entre", "era",
    "esta", "este", "estos", "fecha", "fue", "guardia", "hecho", "instalacion", "la", "las",
    "los", "mas", "para", "pero", "por", "que", "se", "sin", "sobre", "sus", "una", "uno",
    "y", "ya",
}


class AmonestacionGenerationError(RuntimeError):
    pass


def _normalized_words(text):
    normalized = unicodedata.normalize("NFD", str(text or ""))
    normalized = "".join(char for char in normalized if unicodedata.category(char) != "Mn").lower()
    return {
        word for word in re.findall(r"[a-z0-9]{3,}", normalized)
        if word not in STOP_WORDS
    }


def _document_chunks(text):
    text = str(text or "").strip()
    if len(text) <= CHUNK_SIZE:
        return [text] if text else []

    chunks = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        if end < len(text):
            boundary = max(text.rfind("\n\n", start, end), text.rfind("\n", start, end))
            if boundary > start + (CHUNK_SIZE // 2):
                end = boundary
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return chunks


def seleccionar_contexto_relevante(text, consulta, max_chars=MAX_DOCUMENT_CONTEXT_CHARS):
    """Recuperación léxica local: evita enviar documentos completos y no inventa contenido."""
    query_words = _normalized_words(consulta)
    ranked = []
    for position, chunk in enumerate(_document_chunks(text)):
        chunk_words = _normalized_words(chunk)
        matches = query_words & chunk_words
        score = sum(3 if len(word) >= 7 else 1 for word in matches)
        if re.search(r"(?i)\b(art[ií]culo|cl[aá]usula|t[ií]tulo)\b", chunk):
            score += 2
        ranked.append((score, position, chunk))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    selected = []
    used = 0
    for score, position, chunk in ranked:
        if selected and score <= 0:
            break
        available = max_chars - used
        if available <= 0:
            break
        excerpt = chunk[:available]
        selected.append((position, excerpt))
        used += len(excerpt)

    # Mantiene el orden original para que títulos y cláusulas conserven continuidad lógica.
    selected.sort(key=lambda item: item[0])
    return "\n\n[... fragmento separado ...]\n\n".join(chunk for _, chunk in selected)

SYSTEM_PROMPT = """Eres un abogado laboral especializado en legislación chilena, derecho laboral, seguridad privada y redacción de documentos disciplinarios para empresas.

Tu función es redactar exclusivamente Cartas de Amonestación para trabajadores de INOUT Seguridad SpA.

Debes redactar documentos con un lenguaje jurídico, formal, profesional, objetivo y respetuoso, evitando afirmaciones exageradas o hechos que no hayan sido proporcionados.

La carta debe estar preparada para ser impresa y firmada.

La estructura debe ser SIEMPRE la siguiente, en formato compacto y continuo:

1. Ciudad y fecha, en una sola línea.
2. Destinatario: SEÑOR, nombre completo en mayúsculas, C.I., PRESENTE.
3. Referencia: "Ref.: Carta de Amonestación".
4. Saludo: "De nuestra consideración:".
5. Introducción formal breve.
6. Uno o dos párrafos concisos que relaten los hechos y el riesgo operacional.
7. Fundamentos del Contrato de Trabajo, enumerados únicamente cuando existan varias cláusulas.
8. Fundamentos del Reglamento Interno, agrupados en un párrafo breve o enumerados si es necesario.
9. Aplicación de la AMONESTACIÓN ESCRITA y advertencia por reiteración, en un único párrafo.
10. Firma del empleador y trabajador.

REGLAS OBLIGATORIAS

Nunca inventes hechos ni información no entregada. Si se indica reincidencia, menciónala expresamente; si no existe, no la insinúes. Fundamenta siempre utilizando el Contrato de Trabajo y el RIOHS. Para cada fundamento indica el número de artículo, cláusula o letra cuando esté disponible, identifica brevemente la obligación o prohibición y vincúlala con la conducta. No copies literalmente los documentos. Cita únicamente disposiciones realmente aplicables y nunca inventes artículos. Incluye solo las obligaciones directamente pertinentes y aplica el principio de proporcionalidad.

Debe quedar claro qué ocurrió, qué procedimiento fue incumplido, cuál era la obligación del trabajador y cuál fue el riesgo para la empresa o cliente. Cuando corresponda, indica que contrato y reglamento integran la relación laboral.

La sanción siempre será "AMONESTACIÓN ESCRITA". La advertencia final indicará que una reiteración podrá dar lugar a medidas disciplinarias de mayor entidad conforme al Código del Trabajo, el Contrato y el Reglamento Interno.

La extensión ideal es de 450 a 650 palabras y nunca debe superar 750 palabras. Evita repetir los hechos, el riesgo o la conclusión. No crees subtítulos como "Riesgo operacional", "Incumplimientos" o "Aplicación de la sanción"; enlaza esas materias con transiciones naturales como en una carta formal. Usa viñetas solamente para enumerar cláusulas o artículos aplicables. El documento debe tener formato de carta, no de informe. No escribas explicaciones fuera de la carta, no uses Markdown y devuelve únicamente la carta final.

El estilo de referencia es sobrio, moderno y directo: encabezado protocolar, párrafos breves, fundamentos legales concretos y cierre disciplinario en un solo párrafo. Las firmas deben aparecer al final para EMPLEADOR, INOUT SEGURIDAD SpA, RUT 76.435.221-1, y TRABAJADOR con su nombre y RUT."""


def generar_carta(amonestacion, contrato_texto, riohs_texto):
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise AmonestacionGenerationError("El servidor no tiene disponible el servicio de redacción.") from exc

    if not settings.OPENAI_API_KEY:
        raise AmonestacionGenerationError("El servidor no tiene configurado el servicio de redacción.")

    reincidencia = "Sí" if amonestacion.reincidencia else "No"
    consulta = " ".join((
        amonestacion.tipo_incumplimiento,
        amonestacion.descripcion,
        amonestacion.antecedentes or "",
        "obligaciones prohibiciones incumplimiento procedimiento funciones seguridad sanciones amonestación",
    ))
    contrato_contexto = seleccionar_contexto_relevante(contrato_texto, consulta)
    riohs_contexto = seleccionar_contexto_relevante(riohs_texto, consulta)
    if not contrato_contexto or not riohs_contexto:
        raise AmonestacionGenerationError("No se encontró texto utilizable en los documentos laborales.")

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
{contrato_contexto}
--- FIN CONTRATO ---

REGLAMENTO INTERNO DE ORDEN, HIGIENE Y SEGURIDAD:
--- INICIO RIOHS ---
{riohs_contexto}
--- FIN RIOHS ---

Sigue exactamente el formato compacto solicitado por el sistema y evita toda repetición. La carta debe parecerse a una comunicación empresarial redactada por un abogado, no a un informe jurídico. Si los documentos no contienen una disposición aplicable identificable, indícalo brevemente y no inventes una referencia."""

    try:
        response = OpenAI(api_key=settings.OPENAI_API_KEY).responses.create(
            model=getattr(settings, "OPENAI_MODEL", None) or "gpt-4.1-mini",
            input=[
                {"role": "system", "content": [{"type": "input_text", "text": SYSTEM_PROMPT}]},
                {"role": "user", "content": [{"type": "input_text", "text": user_prompt}]},
            ],
            max_output_tokens=2500,
        )
        carta = (getattr(response, "output_text", None) or "").strip()
        if not carta:
            raise RuntimeError("OpenAI no retornó el contenido de la carta.")
        return carta
    except AmonestacionGenerationError:
        raise
    except Exception as exc:
        logger.exception("Error generando carta de amonestación")
        error_code = getattr(exc, "status_code", None)
        if error_code == 429:
            raise AmonestacionGenerationError(
                "OpenAI alcanzó temporalmente el límite de uso. Intenta nuevamente en unos segundos."
            ) from exc
        raise AmonestacionGenerationError(
            "El servicio de redacción no pudo completar la solicitud. Intenta nuevamente."
        ) from exc
