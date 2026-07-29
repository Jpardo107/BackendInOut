import re
import unicodedata

from django.db import migrations


ALIASES = {
    "LOGIS MIRAFLORES": "LOGISFASHION MIRAFLORES",
}


def normalizar(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^A-Z0-9]+", " ", value.upper()).strip()


def vincular_personas(apps, schema_editor):
    PersonalEmpresa = apps.get_model("user", "PersonalEmpresa")
    Instalacion = apps.get_model("instalacion", "Instalacion")

    indice = {}
    ambiguas = set()
    for instalacion in Instalacion.objects.all():
        nombre = normalizar(instalacion.nombre)
        if nombre in indice:
            ambiguas.add(nombre)
        else:
            indice[nombre] = instalacion

    for nombre in ambiguas:
        indice.pop(nombre, None)

    for persona in PersonalEmpresa.objects.filter(instalacion__isnull=True):
        nombre = normalizar(persona.ubicacion)
        instalacion = indice.get(ALIASES.get(nombre, nombre))
        if instalacion:
            persona.instalacion = instalacion
            persona.save(update_fields=["instalacion"])


class Migration(migrations.Migration):
    dependencies = [
        ("user", "0003_personalempresa_instalacion"),
    ]

    operations = [
        migrations.RunPython(vincular_personas, migrations.RunPython.noop),
    ]
