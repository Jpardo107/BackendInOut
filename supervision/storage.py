import uuid
from pathlib import Path

from botocore.exceptions import ClientError
from django.conf import settings
from django.http import FileResponse, Http404, StreamingHttpResponse

from backend_inout.utils.r2_client import get_r2_client

FOTOS_PREFIX = "supervision/fotos/"
# Copias de las fotos que se guardaron en el cPanel: <prefijo><ruta original en el cPanel>.
# El admin usa esta misma convención como respaldo cuando el cPanel no responde.
CPANEL_PREFIX = f"{FOTOS_PREFIX}cpanel"


def _r2_enabled():
    return all([settings.R2_ENDPOINT_URL, settings.R2_ACCESS_KEY_ID, settings.R2_SECRET_ACCESS_KEY, settings.R2_BUCKET_NAME])


def save_supervision_photo(fileobj, name, content_type, key=None):
    """Guarda la foto en R2 (o en MEDIA_ROOT si no hay R2) y devuelve su key."""
    if key is None:
        extension = Path(name or "").suffix.lower() or ".jpg"
        key = f"{FOTOS_PREFIX}{uuid.uuid4().hex}{extension}"
    if _r2_enabled():
        get_r2_client().upload_fileobj(fileobj, settings.R2_BUCKET_NAME, key, ExtraArgs={"ContentType": content_type or "image/jpeg"})
        return key
    local_path = settings.MEDIA_ROOT / key
    local_path.parent.mkdir(parents=True, exist_ok=True)
    with local_path.open("wb") as destination:
        fileobj.seek(0)
        destination.write(fileobj.read())
    return key


def photo_response(key):
    if not key.startswith(FOTOS_PREFIX) or ".." in Path(key).parts:
        raise Http404
    if _r2_enabled():
        try:
            item = get_r2_client().get_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in {"NoSuchKey", "404"}:
                raise Http404 from error
            raise
        response = StreamingHttpResponse(item["Body"].iter_chunks(chunk_size=64 * 1024), content_type=item.get("ContentType") or "application/octet-stream")
        if item.get("ContentLength") is not None:
            response["Content-Length"] = item["ContentLength"]
    else:
        media_root = settings.MEDIA_ROOT.resolve()
        local_path = (media_root / key).resolve()
        if media_root not in local_path.parents or not local_path.is_file():
            raise Http404
        response = FileResponse(local_path.open("rb"))
    response["Cache-Control"] = "public, max-age=86400, immutable"
    response["X-Content-Type-Options"] = "nosniff"
    return response
