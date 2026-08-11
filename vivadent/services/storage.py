import uuid
from pathlib import Path

import boto3
from django.conf import settings


def save_uploaded_image(uploaded_file):
    extension = Path(uploaded_file.name).suffix.lower() or ".jpg"
    key = f"vivadent/images/{uuid.uuid4().hex}{extension}"
    public_base = getattr(settings, "R2_PUBLIC_BASE_URL", "").rstrip("/")
    if all([settings.R2_ENDPOINT_URL, settings.R2_ACCESS_KEY_ID, settings.R2_SECRET_ACCESS_KEY, settings.R2_BUCKET_NAME, public_base]):
        client = boto3.client("s3", endpoint_url=settings.R2_ENDPOINT_URL, aws_access_key_id=settings.R2_ACCESS_KEY_ID, aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY)
        client.upload_fileobj(uploaded_file, settings.R2_BUCKET_NAME, key, ExtraArgs={"ContentType": uploaded_file.content_type or "image/jpeg"})
        return f"{public_base}/{key}"
    local_path = settings.MEDIA_ROOT / key
    local_path.parent.mkdir(parents=True, exist_ok=True)
    with local_path.open("wb") as destination:
        for chunk in uploaded_file.chunks():
            destination.write(chunk)
    return f"{settings.MEDIA_URL}{key}"
