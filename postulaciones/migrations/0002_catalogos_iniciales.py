from django.db import migrations
from django.utils.text import slugify


TIPOS = ["General", "Bodega", "Condominio", "Industrial", "Retail", "Corporativo", "Salud", "Educacional", "CCTV"]
PREGUNTAS = {
    "General": [
        "Una persona afirma ser gerente de la instalación, pero no aparece autorizada. ¿Qué debería hacer?",
        "Durante una ronda encuentra una puerta abierta sin explicación. ¿Cuál es su primera acción?",
        "¿Qué información considera esencial registrar en un libro de novedades?",
    ],
    "Bodega": [
        "¿Qué verificaciones realizaría antes de autorizar la salida de un camión?",
        "Detecta un sello de carga manipulado. ¿Qué procedimiento seguiría?",
        "¿Cómo controlaría el ingreso de proveedores fuera del horario programado?",
    ],
    "Condominio": [
        "Un residente solicita autorizar verbalmente el ingreso de una visita. ¿Qué haría?",
        "¿Cómo actuaría frente a un conflicto entre residentes en un espacio común?",
        "Llega un repartidor y el residente no responde. ¿Qué procedimiento aplicaría?",
    ],
}


def cargar_catalogos(apps, schema_editor):
    Tipo = apps.get_model("postulaciones", "TipoInstalacionLaboral")
    Pregunta = apps.get_model("postulaciones", "PreguntaPostulacion")
    tipos = {}
    for orden, nombre in enumerate(TIPOS):
        tipo, _ = Tipo.objects.get_or_create(
            slug=slugify(nombre),
            defaults={"nombre": nombre, "orden": orden, "activo": True},
        )
        tipos[nombre] = tipo
    for nombre, preguntas in PREGUNTAS.items():
        for orden, texto in enumerate(preguntas):
            Pregunta.objects.get_or_create(
                texto=texto,
                defaults={
                    "tipo_instalacion": tipos[nombre],
                    "tipo_respuesta": "situacional",
                    "puntaje": 0,
                    "orden": orden,
                    "obligatoria": True,
                    "activo": True,
                },
            )


class Migration(migrations.Migration):
    dependencies = [("postulaciones", "0001_initial")]
    operations = [migrations.RunPython(cargar_catalogos, migrations.RunPython.noop)]
