import uuid
from pathlib import Path

from django.conf import settings

from backend_inout.utils.r2_client import get_r2_client


def save_uploaded_image(uploaded_file):
    extension = Path(uploaded_file.name).suffix.lower() or ".jpg"
    key = f"vivadent/images/{uuid.uuid4().hex}{extension}"
    if all([settings.R2_ENDPOINT_URL, settings.R2_ACCESS_KEY_ID, settings.R2_SECRET_ACCESS_KEY, settings.R2_BUCKET_NAME]):
        client = get_r2_client()
        client.upload_fileobj(uploaded_file, settings.R2_BUCKET_NAME, key, ExtraArgs={"ContentType": uploaded_file.content_type or "image/jpeg"})
        return f"/api/vivadent/public/media/{key}"
    local_path = settings.MEDIA_ROOT / key
    local_path.parent.mkdir(parents=True, exist_ok=True)
    with local_path.open("wb") as destination:
        for chunk in uploaded_file.chunks():
            destination.write(chunk)
    return f"/api/vivadent/public/media/{key}"
