import boto3
from django.conf import settings

def get_r2_client():
    missing = [
        name
        for name in (
            "R2_ENDPOINT_URL",
            "R2_ACCESS_KEY_ID",
            "R2_SECRET_ACCESS_KEY",
        )
        if not getattr(settings, name, None)
    ]
    if missing:
        raise RuntimeError(f"Faltan variables R2: {', '.join(missing)}")

    return boto3.client(
        "s3",
        endpoint_url=settings.R2_ENDPOINT_URL,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        region_name="auto",
    )
