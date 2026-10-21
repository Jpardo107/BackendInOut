from backend_inout.settings import *

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
# Tests patch the storage boundary and must never contact the actual bucket.
R2_BUCKET_NAME = "test-only-installation-documents"
R2_ENDPOINT_URL = "https://storage.invalid"
R2_ACCESS_KEY_ID = "test-only"
R2_SECRET_ACCESS_KEY = "test-only"
