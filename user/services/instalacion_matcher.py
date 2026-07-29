import re
import unicodedata

from instalacion.models import Instalacion


# Variantes históricas conocidas del archivo de carga masiva.
INSTALACION_ALIASES = {
    "LOGIS MIRAFLORES": "LOGISFASHION MIRAFLORES",
}


def normalizar_nombre_instalacion(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^A-Z0-9]+", " ", value.upper()).strip()


def construir_indice_instalaciones(queryset=None):
    instalaciones = queryset if queryset is not None else Instalacion.objects.all()
    indice = {}
    ambiguas = set()

    for instalacion in instalaciones:
        nombre = normalizar_nombre_instalacion(instalacion.nombre)
        if nombre in indice:
            ambiguas.add(nombre)
        else:
            indice[nombre] = instalacion

    for nombre in ambiguas:
        indice.pop(nombre, None)

    return indice


def buscar_instalacion(ubicacion, indice=None):
    indice = indice if indice is not None else construir_indice_instalaciones()
    nombre = normalizar_nombre_instalacion(ubicacion)
    nombre = INSTALACION_ALIASES.get(nombre, nombre)
    return indice.get(nombre)
