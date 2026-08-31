from io import BytesIO
from html import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _text(value, fallback="—"):
    return str(value) if value not in (None, "") else fallback


def _yes_no(value):
    return "Sí" if value else "No"


def _paragraph(value, style):
    return Paragraph(escape(_text(value)).replace("\n", "<br/>"), style)


def generar_ficha_postulante_pdf(postulacion):
    """Genera la misma ficha resumida disponible en el administrador."""
    output = BytesIO()
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(output, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm, bottomMargin=14 * mm)
    story = [_paragraph("Ficha de postulante", styles["Title"]), _paragraph(f"{postulacion.codigo} · {postulacion.nombre_completo}", styles["Normal"]), Spacer(1, 5 * mm)]

    def section(title, rows):
        story.append(_paragraph(title, styles["Heading2"]))
        table = Table([[_paragraph(label, styles["Normal"]), _paragraph(value, styles["Normal"])] for label, value in rows], colWidths=[45 * mm, 125 * mm], repeatRows=0)
        table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#CED4DA")),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F3F6FA")),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.extend([table, Spacer(1, 4 * mm)])

    section("Datos personales", [
        ("RUT", postulacion.rut), ("Nacimiento", postulacion.fecha_nacimiento),
        ("Nacionalidad", postulacion.nacionalidad), ("Teléfono", postulacion.telefono),
        ("Correo", postulacion.email), ("Domicilio", f"{_text(postulacion.direccion)} · {_text(postulacion.comuna_residencia)}"),
        ("Situación migratoria", postulacion.situacion_migratoria), ("Estado postulación", postulacion.get_estado_display()),
    ])
    section("Disponibilidad y acreditaciones", [
        ("OS10", f"{postulacion.get_estado_os10_display()}{f' · vence {postulacion.os10_vencimiento}' if postulacion.os10_vencimiento else ''}{f' · N° {postulacion.os10_numero}' if postulacion.os10_numero else ''}"),
        ("Turnos", f"Día: {_yes_no(postulacion.disponible_dia)} · Noche: {_yes_no(postulacion.disponible_noche)} · 4x4: {_yes_no(postulacion.disponible_4x4)} · 5x2: {_yes_no(postulacion.disponible_5x2)}"),
        ("Licencia", f"Sí · clase {_text(postulacion.clase_licencia)}" if postulacion.tiene_licencia else "No"),
        ("Movilización propia", _yes_no(postulacion.movilizacion_propia)), ("Disponible desde", postulacion.disponibilidad_incorporacion),
    ])
    section("Presentación", [("Resumen", postulacion.presentacion)])
    preferencias = [(f"Preferencia {p.orden_preferencia}", f"{p.vacante.descripcion_publica} · {p.vacante.instalacion.nombre} · {p.vacante.comuna_publica} · {p.vacante.jornada} {p.vacante.sistema_turno}") for p in postulacion.preferencias.select_related("vacante__instalacion")]
    section("Preferencias", preferencias or [("", "Sin preferencias")])
    formacion = [("Estudio", f"{x.nivel_educacional} · {x.institucion} · {_text(x.carrera_especialidad)}") for x in postulacion.estudios.all()]
    formacion += [("Curso", f"{x.nombre} · {_text(x.institucion)} · {_text(x.estado)}") for x in postulacion.cursos.all()]
    section("Estudios y cursos", formacion or [("", "Sin registros")])
    experiencias = [(x.cargo, f"{x.empresa} · {x.fecha_inicio} a {'actualidad' if x.trabajo_actual else _text(x.fecha_termino)}\n{x.funciones}") for x in postulacion.experiencias.all()]
    section("Experiencia laboral", experiencias or [("", "Sin registros")])
    section("Documentación", [(x.tipo_documento, f"{x.nombre_original} · {x.estado}") for x in postulacion.documentos.all()] or [("", "Sin documentos")])
    try:
        preguntas = [(x.pregunta_origen.texto, _text(x.respuesta.respuesta)) for x in postulacion.evaluacion.preguntas_asignadas.select_related("pregunta_origen", "respuesta")]
    except Exception:
        preguntas = []
    section("Evaluación", preguntas or [("", "Sin evaluación")])
    doc.build(story)
    return output.getvalue()
