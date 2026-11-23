"""Decide si el texto del campo "solicitudes" es un requerimiento real o una forma de decir que no hay."""
import re
import unicodedata

# "Sin solicitudes", "No hay solicitudes", "Sin solicitud", "Ninguna", "No", "N/A", "Sin novedad", etc.
_SIN_SOLICITUD = re.compile(
    r"^(?:"
    r"(?:sin|no hay|no existen?|no se registran?|no tiene|no|ninguna?|ninguno|nada)"
    r"(?: (?:solicitud(?:es)?|requerimientos?|pedidos?|novedad(?:es)?|observacion(?:es)?))?"
    r"(?: (?:por ahora|pendientes?|para (?:esta|la) instalacion))?"
    r"|n/?a|s/?s|no aplica|-+|\.+"
    r")$"
)


def es_solicitud_real(texto):
    normalizado = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    normalizado = " ".join(normalizado.split()).strip(" .,;:!")
    return bool(normalizado) and not _SIN_SOLICITUD.match(normalizado)
