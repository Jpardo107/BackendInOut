"""One-off, explicit reset of installation documents; never run automatically on deploy."""
import json
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from backend_inout.utils.r2_client import get_r2_client
from documentacion.models import DocumentoInstalacion, TipoDocumentoInstalacion
from documentacion.services.r2_storage import validate_r2_settings

PREFIXES = ("documentos/instalacion_", "documentos/previews/instalacion_")
SCOPED_KEY = re.compile(r"^documentos/(?:previews/)?instalacion_[0-9]+/[^\x00]+$")
CONFIRM = "REINICIAR_DOCUMENTACION_INSTALACIONES"


def installation_key(key):
    return bool(SCOPED_KEY.fullmatch(key or ""))


def preview_key(doc):
    return f"documentos/previews/instalacion_{doc.instalacion_id}/documento_{doc.id}.pdf"


class Command(BaseCommand):
    help = "Inventaría o elimina todos los archivos, vistas previas y tipos de documentación de instalaciones. No toca supervisiones ni otros módulos."

    def add_arguments(self, parser):
        parser.add_argument("--execute", action="store_true", help="Ejecutar la eliminación; por defecto solo inventaría.")
        parser.add_argument("--confirm", default="")
        parser.add_argument("--manifest", help="Archivo JSON NUEVO para registrar el inventario antes de eliminar.")
        parser.add_argument("--allow-sqlite", action="store_true", help="Solo para bases SQLite aisladas; no usar para limpiar un bucket de producción desde una base local.")

    def handle(self, *args, **options):
        execute = options["execute"]
        if execute and options["confirm"] != CONFIRM:
            raise CommandError(f"Para ejecutar, agrega --confirm {CONFIRM}.")
        if execute and connection.vendor == "sqlite" and not options["allow_sqlite"]:
            raise CommandError("La base actual es SQLite. Ejecuta la limpieza desde la consola de producción con su DATABASE_URL; no desde una copia local.")
        if execute and not options["manifest"]:
            raise CommandError("Indica --manifest /ruta/nueva.json para conservar un inventario del reinicio.")

        validate_r2_settings()
        client = get_r2_client()
        docs = list(DocumentoInstalacion.objects.order_by("id"))
        # Never infer another module's ownership from a broad bucket prefix.
        invalid = [doc.id for doc in docs if not installation_key(doc.storage_key)]
        if invalid:
            raise CommandError(f"Hay registros con rutas fuera de documentos/instalacion_ID/: {invalid}. Revisa su pertenencia antes de eliminarlos.")
        objects = {}
        for prefix in PREFIXES:
            for page in client.get_paginator("list_objects_v2").paginate(Bucket=settings.R2_BUCKET_NAME, Prefix=prefix):
                for obj in page.get("Contents", []):
                    if installation_key(obj["Key"]):
                        objects[obj["Key"]] = {"key": obj["Key"], "size": obj["Size"], "etag": obj.get("ETag", "")}
        catalog = list(TipoDocumentoInstalacion.objects.values("id", "codigo", "nombre", "orden"))
        manifest = {"created_at": timezone.now().isoformat(), "database_engine": connection.vendor,
            "bucket": settings.R2_BUCKET_NAME, "types": catalog, "objects": list(objects.values()),
            "documents": [{"id": doc.pk, "instalacion": doc.instalacion_id, "titulo": doc.titulo,
                "categoria": doc.categoria, "storage_key": doc.storage_key, "preview_key": preview_key(doc)} for doc in docs]}
        self.stdout.write(f"Registros: {len(docs)} · Tipos: {len(catalog)} · Objetos R2: {len(objects)} · Bytes: {sum(o['size'] for o in objects.values())}")
        if options["manifest"]:
            path = Path(options["manifest"])
            try:
                with path.open("x", encoding="utf-8") as output:
                    json.dump(manifest, output, ensure_ascii=False, indent=2)
                path.chmod(0o600)
            except OSError as exc:
                raise CommandError(f"No se pudo crear el inventario: {exc}") from exc
        if not execute:
            self.stdout.write("Solo inventario. No se ha eliminado ningún archivo ni registro.")
            return

        failures = []
        processed = set()
        # Each successful row commits separately. A failed object retains its row for retry.
        for snapshot in docs:
            try:
                with transaction.atomic():
                    doc = DocumentoInstalacion.objects.select_for_update().filter(pk=snapshot.pk).first()
                    if not doc:
                        continue
                    if doc.storage_key != snapshot.storage_key:
                        raise RuntimeError("El documento cambió después del inventario")
                    keys = (preview_key(doc), doc.storage_key)
                    for key in keys:
                        client.delete_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
                    doc.delete()
                    processed.update(keys)
            except Exception:
                failures.append(f"registro {snapshot.pk}")

        protected = set(DocumentoInstalacion.objects.values_list("storage_key", flat=True))
        protected.update(preview_key(doc) for doc in DocumentoInstalacion.objects.all())
        orphan_keys = sorted(set(objects) - processed - protected)
        for start in range(0, len(orphan_keys), 1000):
            keys = orphan_keys[start:start + 1000]
            try:
                result = client.delete_objects(Bucket=settings.R2_BUCKET_NAME, Delete={"Objects": [{"Key": key} for key in keys], "Quiet": True})
                failures.extend(item.get("Key", "objeto R2") for item in result.get("Errors", []))
            except Exception:
                failures.append(f"lote de {len(keys)} objetos huérfanos")

        if failures or DocumentoInstalacion.objects.exists():
            raise CommandError(f"Limpieza incompleta: {len(failures)} errores; quedan {DocumentoInstalacion.objects.count()} registros. El catálogo se conserva. Reintenta con un inventario nuevo; no restaures los registros ya eliminados.")
        # Delete only the catalog entries inventoried, preserving any newly-created requirements.
        with transaction.atomic():
            types = list(TipoDocumentoInstalacion.objects.select_for_update().filter(pk__in=[t["id"] for t in catalog]))
            for tipo in types:
                if tipo.documentos.exists():
                    raise CommandError("Se cargaron documentos durante el reinicio. Repite con las cargas detenidas.")
                tipo.delete()
        remaining = 0
        for prefix in PREFIXES:
            for page in client.get_paginator("list_objects_v2").paginate(Bucket=settings.R2_BUCKET_NAME, Prefix=prefix):
                remaining += sum(installation_key(obj["Key"]) for obj in page.get("Contents", []))
        if remaining or TipoDocumentoInstalacion.objects.exists() or DocumentoInstalacion.objects.exists():
            raise CommandError("Se encontraron archivos o registros nuevos al verificar. Repite el inventario con las cargas detenidas.")
        self.stdout.write(self.style.SUCCESS("Verificado: 0 archivos R2, 0 documentos de instalaciones y 0 tipos. Catálogo listo para empezar desde cero."))
