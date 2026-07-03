from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from .rut import normalizar_rut

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def column_number(cell_ref):
    letters = "".join(ch for ch in cell_ref if ch.isalpha())
    number = 0
    for letter in letters:
        number = number * 26 + ord(letter.upper()) - 64
    return number


def load_shared_strings(zip_file):
    try:
        root = ET.fromstring(zip_file.read("xl/sharedStrings.xml"))
    except KeyError:
        return []

    ns = {"m": MAIN_NS}
    values = []
    for item in root.findall("m:si", ns):
        values.append("".join(node.text or "" for node in item.findall(".//m:t", ns)))
    return values


def first_sheet_path(zip_file):
    ns = {"m": MAIN_NS, "r": REL_NS, "rel": PKG_REL_NS}
    workbook = ET.fromstring(zip_file.read("xl/workbook.xml"))
    rels = ET.fromstring(zip_file.read("xl/_rels/workbook.xml.rels"))
    rel_by_id = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels.findall("rel:Relationship", ns)
    }
    sheet = workbook.find("m:sheets/m:sheet", ns)
    rel_id = sheet.attrib[f"{{{REL_NS}}}id"]
    target = rel_by_id[rel_id]
    return f"xl/{target.lstrip('/')}" if not target.startswith("xl/") else target


def read_rows(file_obj):
    with ZipFile(file_obj) as zip_file:
        shared_strings = load_shared_strings(zip_file)
        sheet_path = first_sheet_path(zip_file)
        root = ET.fromstring(zip_file.read(sheet_path))

    ns = {"m": MAIN_NS}
    rows = []

    for row in root.findall("m:sheetData/m:row", ns):
        values = {}
        for cell in row.findall("m:c", ns):
            index = column_number(cell.attrib.get("r", ""))
            cell_type = cell.attrib.get("t")
            value_node = cell.find("m:v", ns)

            if value_node is None:
                value = ""
            elif cell_type == "s":
                value = shared_strings[int(value_node.text)]
            elif cell_type == "inlineStr":
                value = "".join(node.text or "" for node in cell.findall(".//m:t", ns))
            else:
                value = value_node.text or ""

            values[index] = str(value).strip()

        if values:
            rows.append([values.get(index, "") for index in range(1, max(values) + 1)])

    return rows


def parse_personal_excel(file_obj):
    rows = read_rows(file_obj)
    personal = []
    errores = []

    for row_number, row in enumerate(rows, start=1):
        rut = normalizar_rut(row[0] if len(row) > 0 else "")
        nombre = str(row[1] if len(row) > 1 else "").strip()
        ubicacion = str(row[2] if len(row) > 2 else "").strip()

        if row_number == 1 and not rut:
            continue

        if not rut or not nombre:
            errores.append({
                "fila": row_number,
                "detalle": "Fila omitida por RUT o nombre invalido.",
            })
            continue

        personal.append({
            "rut": rut,
            "nombre_completo": " ".join(nombre.split()).upper(),
            "ubicacion": " ".join(ubicacion.split()).upper(),
        })

    return personal, errores
