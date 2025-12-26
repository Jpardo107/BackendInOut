from backend_inout.utils.r2_client import get_r2_client
from django.core.files.uploadedfile import UploadedFile
from django.conf import settings


def upload_document(file: UploadedFile, key: str):
    client = get_r2_client()

    client.put_object(
        Bucket=settings.R2_BUCKET_NAME,
        Key=key,
        Body=file,
        ContentType=file.content_type,
    )

    return key

def generate_signed_url(key: str, expires=60):
    client = get_r2_client()

    url = client.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": settings.R2_BUCKET_NAME,
            "Key": key,
        },
        ExpiresIn=expires,  # segundos
    )

    return url
