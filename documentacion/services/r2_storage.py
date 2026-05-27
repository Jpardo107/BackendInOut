from backend_inout.utils.r2_client import get_r2_client
from django.core.files.uploadedfile import UploadedFile
from django.conf import settings
from urllib.parse import quote


def upload_document(file: UploadedFile, key: str):
    client = get_r2_client()

    client.put_object(
        Bucket=settings.R2_BUCKET_NAME,
        Key=key,
        Body=file,
        ContentType=file.content_type,
    )

    return key

def upload_file_path(path: str, key: str, content_type: str):
    client = get_r2_client()

    with open(path, "rb") as file:
        client.put_object(
            Bucket=settings.R2_BUCKET_NAME,
            Key=key,
            Body=file,
            ContentType=content_type,
        )

    return key

def download_document_to_path(key: str, path: str):
    client = get_r2_client()

    with open(path, "wb") as file:
        client.download_fileobj(settings.R2_BUCKET_NAME, key, file)

def download_document_to_fileobj(key: str, fileobj):
    client = get_r2_client()

    client.download_fileobj(settings.R2_BUCKET_NAME, key, fileobj)

def delete_document(key: str):
    client = get_r2_client()

    client.delete_object(
        Bucket=settings.R2_BUCKET_NAME,
        Key=key,
    )

def generate_signed_url(key: str, expires=60, filename=None, disposition=None):
    client = get_r2_client()

    params = {
        "Bucket": settings.R2_BUCKET_NAME,
        "Key": key,
    }

    if filename and disposition:
        encoded_filename = quote(filename)
        fallback_filename = filename.encode("ascii", errors="ignore").decode("ascii")
        fallback_filename = fallback_filename.replace('"', "").strip() or "documento"
        params["ResponseContentDisposition"] = (
            f'{disposition}; filename="{fallback_filename}"; filename*=UTF-8\'\'{encoded_filename}'
        )

    url = client.generate_presigned_url(
        "get_object",
        Params=params,
        ExpiresIn=expires,  # segundos
    )

    return url
