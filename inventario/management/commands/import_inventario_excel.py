from collections import OrderedDict
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from django.core.management.base import BaseCommand, CommandError

from inventario.models import PrendaInventario
from inventario.services.codigos import generar_codigo_barra, generar_codigo_qr, normalizar_texto


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
    strings = []
    for item in root.findall("m:si", ns):
        text = "".join(node.text or "" for node in item.findall(".//m:t", ns))
        strings.append(text)
    return strings


def get_sheet_path(zip_file, sheet_name):
    ns = {"m": MAIN_NS, "r": REL_NS, "rel": PKG_REL_NS}
    workbook = ET.fromstring(zip_file.read("xl/workbook.xml"))
    rels = ET.fromstring(zip_file.read("xl/_rels/workbook.xml.rels"))

    rel_by_id = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels.findall("rel:Relationship", ns)
    }

    for sheet in workbook.findall("m:sheets/m:sheet", ns):
        if sheet.attrib.get("name") != sheet_name:
            continue
        rel_id = sheet.attrib[f"{{{REL_NS}}}id"]
        target = rel_by_id[rel_id]
        return f"xl/{target.lstrip('/')}" if not target.startswith("xl/") else target

    raise CommandError(f"No existe la hoja {sheet_name!r} en el archivo.")


def read_sheet_rows(path, sheet_name):
    with ZipFile(path) as zip_file:
        shared_strings = load_shared_strings(zip_file)
        sheet_path = get_sheet_path(zip_file, sheet_name)
        root = ET.fromstring(zip_file.read(sheet_path))

    ns = {"m": MAIN_NS}
    rows = []
    for row in root.findall("m:sheetData/m:row", ns):
        values = {}
        for cell in row.findall("m:c", ns):
            ref = cell.attrib.get("r", "")
            index = column_number(ref)
            cell_type = cell.attrib.get("t")
            value_node = cell.find("m:v", ns)

            if value_node is None:
                value = ""
            elif cell_type == "s":
                value = shared_strings[int(value_node.text)]
            else:
                value = value_node.text or ""

            values[index] = str(value).strip()

        if values:
            max_col = max(values)
            rows.append([values.get(index, "") for index in range(1, max_col + 1)])

    return rows


class Command(BaseCommand):
    help = "Importa el stock inicial de uniformes desde el Excel de inventario."

    def add_arguments(self, parser):
        parser.add_argument(
            "archivo",
            nargs="?",
            default="../Inventario_Uniformes_2026.xlsx",
            help="Ruta al archivo .xlsx. Por defecto usa ../Inventario_Uniformes_2026.xlsx",
        )
        parser.add_argument(
            "--sheet",
            default="INVENTARIOEPP",
            help="Nombre de la hoja a importar.",
        )
        parser.add_argument(
            "--stock-critico",
            type=int,
            default=5,
            help="Stock critico por defecto para cada prenda+talla.",
        )

    def handle(self, *args, **options):
        path = Path(options["archivo"])
        if not path.is_absolute():
            path = Path.cwd() / path
        path = path.resolve()

        if not path.exists():
            raise CommandError(f"No existe el archivo: {path}")

        rows = read_sheet_rows(path, options["sheet"])
        if not rows:
            raise CommandError("La hoja no contiene filas.")

        headers = [normalizar_texto(value) for value in rows[0]]
        try:
            prenda_index = headers.index("PRENDA")
            talla_index = headers.index("TALLA")
            cantidad_index = headers.index("CANTIDAD")
        except ValueError as exc:
            raise CommandError("La hoja debe contener las columnas PRENDA, TALLA y CANTIDAD.") from exc

        grouped = OrderedDict()
        skipped = 0

        for row in rows[1:]:
            nombre = row[prenda_index].strip() if len(row) > prenda_index else ""
            talla = row[talla_index].strip() if len(row) > talla_index else ""
            cantidad_raw = row[cantidad_index].strip() if len(row) > cantidad_index else "0"

            if not nombre or not talla:
                skipped += 1
                continue

            try:
                cantidad = int(float(cantidad_raw or 0))
            except ValueError:
                skipped += 1
                continue

            nombre_normalizado = normalizar_texto(nombre)
            talla_normalizada = normalizar_texto(talla)
            key = (nombre_normalizado, talla_normalizada)

            if key not in grouped:
                grouped[key] = {
                    "nombre_prenda": nombre_normalizado,
                    "talla_prenda": talla_normalizada,
                    "cantidad": 0,
                }

            grouped[key]["cantidad"] += max(cantidad, 0)

        created = 0
        updated = 0

        for (nombre_normalizado, talla_normalizada), item in grouped.items():
            codigo_barra = generar_codigo_barra(item["nombre_prenda"], item["talla_prenda"])
            codigo_qr = generar_codigo_qr(codigo_barra)
            defaults = {
                "nombre_prenda": item["nombre_prenda"],
                "talla_prenda": item["talla_prenda"],
                "cantidad_prenda": item["cantidad"],
                "stock_actual": item["cantidad"],
                "stock_critico": options["stock_critico"],
                "codigo_barra": codigo_barra,
                "codigo_qr": codigo_qr,
                "activo": True,
            }
            _, was_created = PrendaInventario.objects.update_or_create(
                nombre_normalizado=nombre_normalizado,
                talla_normalizada=talla_normalizada,
                defaults=defaults,
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Inventario importado: {created} creados, {updated} actualizados, {skipped} filas omitidas."
            )
        )
