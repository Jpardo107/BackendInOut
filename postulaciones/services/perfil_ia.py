import json
import logging

from django.conf import settings

from documentacion.services.r2_storage import generate_signed_url


logger = logging.getLogger(__name__)

ANALISIS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["score_curriculum", "score_evaluacion", "resumen", "fortalezas", "aspectos_a_validar"],
    "properties": {
        "score_curriculum": {"type": "integer", "minimum": 0, "maximum": 20},
        "score_evaluacion": {"type": "integer", "minimum": 0, "maximum": 20},
        "resumen": {"type": "string"},
        "fortalezas": {"type": "array", "items": {"type": "string"}},
        "aspectos_a_validar": {"type": "array", "items": {"type": "string"}},
    },
}


def analizar_perfil_con_ia(postulacion, vacante):
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("La dependencia openai no está instalada.") from exc
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY no está configurada.")

    respuestas = []
    if hasattr(postulacion, "evaluacion"):
        for pregunta in postulacion.evaluacion.preguntas_asignadas.all():
            respuestas.append({
                "pregunta": pregunta.texto,
                "tipo": pregunta.tipo_instalacion_nombre,
                "respuesta": getattr(getattr(pregunta, "respuesta", None), "respuesta", None),
            })
    antecedentes = {
        "presentacion": postulacion.presentacion,
        "estado_os10": postulacion.estado_os10,
        "estudios": list(postulacion.estudios.values("nivel_educacional", "carrera_especialidad", "estado")),
        "cursos": list(postulacion.cursos.values("nombre", "tipo_curso", "estado")),
        "experiencias": list(postulacion.experiencias.values("cargo", "tipo_instalacion__nombre", "funciones", "fecha_inicio", "fecha_termino")),
        "evaluacion": respuestas,
        "vacante": {
            "descripcion": vacante.descripcion_publica if vacante else "Banco general",
            "tipo": vacante.tipo_instalacion.nombre if vacante else "General",
            "requisitos": vacante.requisitos if vacante else "",
        },
    }
    content = [{"type": "input_text", "text": json.dumps(antecedentes, ensure_ascii=False, default=str)}]
    curriculum = postulacion.documentos.filter(tipo_documento="curriculum").order_by("-creado_en").first()
    if curriculum:
        url = generate_signed_url(curriculum.storage_key, expires=600, filename=curriculum.nombre_original, disposition="inline")
        if curriculum.mime_type == "application/pdf":
            content.append({"type": "input_file", "file_url": url})
        elif curriculum.mime_type.startswith("image/"):
            content.append({"type": "input_image", "image_url": url, "detail": "auto"})

    response = OpenAI(api_key=settings.OPENAI_API_KEY).responses.create(
        model=getattr(settings, "OPENAI_MODEL", None) or "gpt-4.1-mini",
        instructions=(
            "Actúa como apoyo de reclutamiento para guardias de seguridad en Chile. Evalúa únicamente experiencia, "
            "formación, certificaciones, presentación y calidad de las respuestas. No uses edad, nacionalidad, sexo, "
            "situación familiar ni otros atributos protegidos. No inventes datos. El resultado es apoyo para revisión humana, "
            "no una decisión automática. Puntúa currículum y evaluación de 0 a 20 cada uno."
        ),
        input=[{"role": "user", "content": content}],
        text={"format": {"type": "json_schema", "name": "analisis_postulante", "schema": ANALISIS_SCHEMA, "strict": True}},
        store=False,
    )
    if not response.output_text:
        raise RuntimeError("OpenAI no retornó el análisis del perfil.")
    return json.loads(response.output_text)
