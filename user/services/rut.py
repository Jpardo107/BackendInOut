import re


def normalizar_rut(value):
    rut = re.sub(r"[^0-9kK]", "", str(value or "")).upper()
    if len(rut) < 7 or len(rut) > 9:
        return ""
    return rut


def formatear_rut(rut):
    rut = normalizar_rut(rut)
    if len(rut) < 2:
        return rut

    cuerpo = rut[:-1]
    dv = rut[-1]
    partes = []

    while cuerpo:
        partes.insert(0, cuerpo[-3:])
        cuerpo = cuerpo[:-3]

    return f"{'.'.join(partes)}-{dv}"
