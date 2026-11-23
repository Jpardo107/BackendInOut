import io
import mimetypes
from pathlib import PurePosixPath
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse

from supervision.models import FotoSupervision
from supervision.storage import CPANEL_PREFIX, save_supervision_photo


def cpanel_key(url):
    path = unquote(urlparse(url).path)
    if not path.startswith("/") or ".." in PurePosixPath(path).parts:
        raise ValueError(f"Ruta no válida: {url}")
    return f"{CPANEL_PREFIX}{path}"


class Command(BaseCommand):
    help = (
        "Copia a R2 las fotos de supervisión alojadas en el cPanel, en "
        "supervision/fotos/cpanel/<ruta original>, que es donde el admin las busca si el cPanel falla."
    )

    def add_arguments(self, parser):
        parser.add_argument("--host", default="inout.jaimepardo.cl", help="Host antiguo cuyas fotos se copian.")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--actualizar-urls",
            metavar="BASE_URL",
            help="Además reescribe url_imagen para apuntar a R2 (ej: https://backendinout.onrender.com). "
            "Sin esta opción la base de datos no se modifica.",
        )

    def handle(self, *args, host, dry_run, actualizar_urls, **options):
        fotos = [f for f in FotoSupervision.objects.all() if urlparse(f.url_imagen).hostname == host]
        self.stdout.write(f"{len(fotos)} fotos en {host}.")
        errores = 0
        for foto in fotos:
            try:
                key = cpanel_key(foto.url_imagen)
            except ValueError as exc:
                errores += 1
                self.stderr.write(f"Error {foto.pk}: {exc}")
                continue
            if dry_run:
                self.stdout.write(f"[dry-run] {foto.pk}: {foto.url_imagen} -> {key}")
                continue
            try:
                with urlopen(Request(foto.url_imagen, headers={"User-Agent": "inout-migracion"}), timeout=30) as response:
                    data = response.read()
                    content_type = response.headers.get_content_type()
            except Exception as exc:
                errores += 1
                self.stderr.write(f"Error {foto.pk} {foto.url_imagen}: {exc}")
                continue
            if not content_type.startswith("image/"):
                content_type = mimetypes.guess_type(key)[0] or "image/jpeg"
            save_supervision_photo(io.BytesIO(data), key, content_type, key=key)
            if actualizar_urls:
                foto.url_imagen = actualizar_urls.rstrip("/") + reverse("supervision-foto-publica", kwargs={"key": key})
                foto.save(update_fields=["url_imagen"])
            self.stdout.write(f"OK {foto.pk} -> {key}")
        if errores:
            raise CommandError(f"{errores} fotos no se pudieron copiar; vuelve a ejecutar el comando para reintentar.")
