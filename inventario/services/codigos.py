import re
import unicodedata


def normalizar_texto(value):
    texto = str(value or "").strip()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    texto = re.sub(r"\s+", " ", texto)
    return texto.upper()


def slug_inventario(value):
    texto = normalizar_texto(value)
    texto = re.sub(r"[^A-Z0-9]+", "-", texto)
    return texto.strip("-") or "SIN-DATO"


def generar_codigo_barra(nombre_prenda, talla_prenda):
    return f"INV-{slug_inventario(nombre_prenda)}-{slug_inventario(talla_prenda)}"


def generar_codigo_qr(codigo_barra):
    return f"inout://inventario/prenda/{codigo_barra}"
