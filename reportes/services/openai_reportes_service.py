import json
import logging

from django.conf import settings

from documentacion.services.r2_storage import generate_signed_url
from reportes.models import ReporteInforme


logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Eres un experto en seguridad privada, supervision operativa, analisis de vulnerabilidades "
    "fisicas, control de acceso, CCTV, iluminacion, cierre perimetral, procedimientos preventivos "
    "y gestion de riesgos en instalaciones. Debes redactar informes profesionales, claros, sobrios "
    "y orientados a clientes corporativos en Chile. No inventes hechos no observados. Si algo no "
    "puede comprobarse por texto o imagen, indicalo como posible observacion o punto a verificar."
)

VULNERABILIDADES_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "criticidad_general",
        "resumen_ejecutivo",
        "conclusion_profesional",
        "riesgos_detectados",
        "recomendaciones",
        "matriz_riesgo",
        "texto_final_pdf",
    ],
    "properties": {
        "criticidad_general": {"type": "string", "enum": ["baja", "media", "alta", "critica"]},
        "resumen_ejecutivo": {"type": "string"},
        "conclusion_profesional": {"type": "string"},
        "riesgos_detectados": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["riesgo", "evidencia", "probabilidad", "impacto", "nivel"],
                "properties": {
                    "riesgo": {"type": "string"},
                    "evidencia": {"type": "string"},
                    "probabilidad": {"type": "string", "enum": ["baja", "media", "alta"]},
                    "impacto": {"type": "string", "enum": ["bajo", "medio", "alto"]},
                    "nivel": {"type": "string", "enum": ["bajo", "medio", "alto", "critico"]},
                },
            },
        },
        "recomendaciones": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["prioridad", "recomendacion", "justificacion"],
                "properties": {
                    "prioridad": {"type": "string", "enum": ["critica", "alta", "media", "baja"]},
                    "recomendacion": {"type": "string"},
                    "justificacion": {"type": "string"},
                },
            },
        },
        "matriz_riesgo": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["hallazgo", "probabilidad", "impacto", "nivel_riesgo"],
                "properties": {
                    "hallazgo": {"type": "string"},
                    "probabilidad": {"type": "string"},
                    "impacto": {"type": "string"},
                    "nivel_riesgo": {"type": "string"},
                },
            },
        },
        "texto_final_pdf": {"type": "string"},
    },
}


def _get_openai_client():
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("La dependencia openai no esta instalada.") from exc

    api_key = getattr(settings, "OPENAI_API_KEY", None)
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY no esta configurada.")

    return OpenAI(api_key=api_key)


def _image_payload(reporte: ReporteInforme):
    content = []
    for imagen in reporte.imagenes.all().order_by("orden", "id"):
        try:
            url = generate_signed_url(imagen.storage_key, expires=600, disposition="inline")
        except Exception:
            logger.exception("Error generando signed URL reporte")
            raise

        content.append(
            {
                "type": "input_text",
                "text": (
                    f"Imagen {imagen.orden + 1}. "
                    f"Descripcion supervisor: {imagen.descripcion or 'Sin descripcion'}. "
                    f"Recomendacion supervisor: {imagen.recomendacion_usuario or 'Sin recomendacion'}."
                ),
            }
        )
        content.append({"type": "input_image", "image_url": url, "detail": "auto"})
    return content


def _build_user_content(reporte: ReporteInforme):
    policial = "Si" if reporte.personal_policial_presente else "No"
    text = f"""
Genera el analisis profesional para un reporte de vulnerabilidades.

Reglas de analisis:
- Usa descripcion_hechos como analisis previo.
- Usa las descripciones de fotos como evidencia principal.
- Usa recomendaciones por foto como sugerencias del supervisor.
- Usa analisis_final_usuario como base, pero mejoralo profesionalmente.
- En texto_final_pdf incluye una seccion "Evidencia fotografica" con cada imagen numerada.
- En esa seccion conserva la descripcion del supervisor y la recomendacion asociada a cada imagen.
- Si hay imagenes, no omitas la evidencia fotografica aunque el analisis general sea breve.
- No reemplaces completamente el criterio humano.
- Complementa, ordena y profesionaliza.
- Si una imagen no permite concluir algo con certeza, indicalo.
- No inventes ubicacion, personas, hechos delictuales ni responsabilidades.
- No afirmes delitos sin antecedentes.
- Usa lenguaje profesional de seguridad privada.

Datos del reporte:
- Instalacion: {reporte.instalacion.nombre}
- Direccion: {reporte.instalacion.direccion}, {reporte.instalacion.comuna}
- Zona: {reporte.zona}
- Autor: {reporte.autor_nombre}
- Cargo autor: {reporte.autor_cargo}
- Fecha emision: {reporte.fecha_emision}
- Personal presente: {reporte.personal_presente or 'No informado'}
- Personal policial presente: {policial}
- Carabinero/cargo: {reporte.carabinero_cargo or 'No informado'}
- Patente patrulla: {reporte.patente_patrulla or 'No informado'}
- Numero carro policial: {reporte.numero_carro_policial or 'No informado'}
- Descripcion de hechos / analisis previo: {reporte.descripcion_hechos or reporte.analisis_previo}
- Analisis final del supervisor: {reporte.analisis_final_usuario or 'No informado'}

Responde exactamente un JSON con las claves solicitadas por el esquema. No agregues markdown.
""".strip()

    return [{"type": "input_text", "text": text}, *_image_payload(reporte)]


def generar_analisis_vulnerabilidades(reporte: ReporteInforme) -> dict:
    if reporte.tipo_reporte != ReporteInforme.TIPO_VULNERABILIDADES:
        return {}

    model = getattr(settings, "OPENAI_MODEL", None) or "gpt-4.1-mini"

    client = _get_openai_client()

    try:
        response = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": [{"type": "input_text", "text": SYSTEM_PROMPT}]},
                {"role": "user", "content": _build_user_content(reporte)},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "reporte_vulnerabilidades",
                    "schema": VULNERABILIDADES_SCHEMA,
                    "strict": True,
                }
            },
        )

        output_text = getattr(response, "output_text", None)
        if not output_text:
            for item in getattr(response, "output", []) or []:
                for content in getattr(item, "content", []) or []:
                    if getattr(content, "type", "") == "output_text":
                        output_text = getattr(content, "text", "")
                        break
                if output_text:
                    break

        if not output_text:
            raise RuntimeError("OpenAI no retorno texto de salida.")

        data = json.loads(output_text)
        raw = response.model_dump(mode="json") if hasattr(response, "model_dump") else {}
        return {"data": data, "raw": raw}
    except Exception:
        logger.exception("Error generando analisis IA para reporte %s.", reporte.id)
        raise
