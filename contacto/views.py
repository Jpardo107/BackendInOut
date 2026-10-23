import hashlib
import ipaddress
import json
import logging
import time
import uuid
from functools import lru_cache

from django.conf import settings
from django.core.cache import cache
from django.core.mail import EmailMessage
from django.core.validators import EmailValidator
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from redis import Redis

logger = logging.getLogger(__name__)
MAX_REQUEST_BYTES = 20_000
RATE_WINDOW_SECONDS = 60 * 60
MAX_REQUESTS_PER_IP = 5
MAX_REQUESTS_GLOBAL = 500
IDEMPOTENCY_SECONDS = 24 * 60 * 60
PENDING_SECONDS = 60

SERVICES = {
    "Necesito orientación",
    "Seguridad física",
    "Seguridad tecnológica",
    "Supervisión operativa",
    "Servicios especiales",
    "Seguridad para centros logísticos",
    "Seguridad para parques industriales",
    "Seguridad para condominios",
    "Seguridad para edificios corporativos",
    "Seguridad para retail y comercio",
    "Seguridad para eventos",
}
validate_email = EmailValidator()
FIELD_LIMITS = {
    "name": 100,
    "email": 254,
    "phone": 30,
    "company": 150,
    "service": 120,
    "commune": 100,
    "message": 3000,
    "website": 200,
    "request_id": 36,
}


@lru_cache(maxsize=1)
def _redis_client():
    redis_url = getattr(settings, "REDIS_URL", "")
    if not redis_url:
        return None
    return Redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)


def _response(status, **data):
    response = JsonResponse(data, status=status)
    response["Cache-Control"] = "no-store"
    return response


def _validate(payload):
    if not isinstance(payload, dict):
        return None
    values = {}
    for field, limit in FIELD_LIMITS.items():
        value = payload.get(field, "")
        if not isinstance(value, str) or len(value) > limit:
            return None
        if "\x00" in value:
            return None
        value = value.replace("\r\n", "\n").replace("\r", "\n").strip()
        if field not in {"message"} and "\n" in value:
            return None
        values[field] = value

    if values["website"]:
        return None
    if len(values["name"]) < 2 or len(values["message"]) < 10:
        return None
    if values["service"] not in SERVICES:
        return None
    try:
        validate_email(values["email"])
    except ValidationError:
        return None
    try:
        request_id = uuid.UUID(values["request_id"])
    except (ValueError, AttributeError):
        return None
    if request_id.version != 4:
        return None
    values["request_id"] = str(request_id)
    return values


def _allow_request(client_key):
    """A single Redis script enforces both limits across Render instances."""
    redis_client = _redis_client()
    if redis_client is not None:
        script = """
        local ip_count = redis.call('INCR', KEYS[1])
        if ip_count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
        if ip_count > tonumber(ARGV[2]) then return 1 end
        local global_count = redis.call('INCR', KEYS[2])
        if global_count == 1 then redis.call('EXPIRE', KEYS[2], ARGV[1]) end
        if global_count > tonumber(ARGV[3]) then return 2 end
        return 0
        """
        result = redis_client.eval(
            script,
            2,
            f"contact:rate:ip:{client_key}",
            f"contact:rate:global:{int(time.time() // RATE_WINDOW_SECONDS)}",
            RATE_WINDOW_SECONDS,
            MAX_REQUESTS_PER_IP,
            MAX_REQUESTS_GLOBAL,
        )
        return int(result) == 0

    # Local development fallback. Render config already requires REDIS_URL.
    hour = int(time.time() // RATE_WINDOW_SECONDS)
    ip_key = f"contact:rate:ip:{hour}:{client_key}"
    global_key = f"contact:rate:global:{hour}"
    if not cache.add(ip_key, 1, timeout=RATE_WINDOW_SECONDS):
        if cache.incr(ip_key) > MAX_REQUESTS_PER_IP:
            return False
    if not cache.add(global_key, 1, timeout=RATE_WINDOW_SECONDS):
        if cache.incr(global_key) > MAX_REQUESTS_GLOBAL:
            return False
    return True


def _release_pending(client, key, token):
    if client is not None:
        client.eval(
            "if redis.call('GET', KEYS[1]) == ARGV[1] then "
            "return redis.call('DEL', KEYS[1]) else return 0 end",
            1,
            key,
            token,
        )
    elif cache.get(key) == token:
        cache.delete(key)


@csrf_exempt
@require_POST
def cotizacion(request):
    """Public intake for commercial quote requests; separate from candidate applications."""
    content_length = request.META.get("CONTENT_LENGTH", "")
    try:
        if content_length and int(content_length) > MAX_REQUEST_BYTES:
            return _response(413, ok=False, error="too_large")
    except ValueError:
        return _response(400, ok=False, error="invalid_content_length")
    if len(request.body) > MAX_REQUEST_BYTES:
        return _response(413, ok=False, error="too_large")
    if request.content_type != "application/json":
        return _response(415, ok=False, error="json_required")

    origins = getattr(
        settings,
        "CONTACT_ALLOWED_ORIGINS",
        ("https://www.inout.cl", "https://inout.cl"),
    )
    origin = request.headers.get("Origin", "").rstrip("/")
    if not origin or origin not in origins:
        return _response(403, ok=False, error="origin_not_allowed")

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _response(400, ok=False, error="invalid_json")
    data = _validate(payload)
    if data is None:
        return _response(422, ok=False, error="invalid_fields")

    # Render sits behind a proxy and sets X-Forwarded-For with the client first.
    # The global Redis limit also bounds requests if a caller forges this header.
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    ip_address = forwarded_for.split(",", 1)[0].strip() or request.META.get(
        "REMOTE_ADDR", "unknown"
    )
    try:
        ip_address = str(ipaddress.ip_address(ip_address))
    except ValueError:
        ip_address = request.META.get("REMOTE_ADDR", "unknown")
    ip_key = hashlib.sha256(ip_address.encode("utf-8", "replace")).hexdigest()
    request_key = hashlib.sha256(data["request_id"].encode()).hexdigest()
    fingerprint = hashlib.sha256(
        json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    try:
        redis_client = _redis_client()
        sent_key = f"contact:sent:{request_key}"
        pending_key = f"contact:pending:{request_key}"
        if redis_client is not None:
            sent_fingerprint = redis_client.get(sent_key)
            claim = lambda token: redis_client.set(
                pending_key, token, ex=PENDING_SECONDS, nx=True
            )
            reserve = lambda token: bool(claim(token))
        else:
            sent_fingerprint = cache.get(sent_key)
            reserve = lambda token: cache.add(
                pending_key, token, timeout=PENDING_SECONDS
            )
        if sent_fingerprint is not None:
            if sent_fingerprint == fingerprint:
                return _response(202, ok=True)
            return _response(422, ok=False, error="request_changed")
        token = uuid.uuid4().hex
        if not reserve(token):
            return _response(409, ok=False, error="request_in_progress")
        if not _allow_request(ip_key):
            _release_pending(redis_client, pending_key, token)
            return _response(429, ok=False, error="rate_limited")

        backend = settings.EMAIL_BACKEND
        sender = settings.DEFAULT_FROM_EMAIL
        if (
            not backend.endswith("django.core.mail.backends.smtp.EmailBackend")
            or not settings.EMAIL_HOST
            or settings.EMAIL_HOST.lower() in {"localhost", "127.0.0.1"}
            or not settings.EMAIL_HOST_USER
            or not settings.EMAIL_HOST_PASSWORD
            or not sender
        ):
            _release_pending(redis_client, pending_key, token)
            logger.error("Commercial contact email transport is not configured.")
            return _response(503, ok=False, error="email_not_configured")

        message = EmailMessage(
            subject="Nueva solicitud comercial desde inout.cl",
            body=(
                "NUEVA SOLICITUD DE COTIZACIÓN\n\n"
                f"Nombre: {data['name']}\n"
                f"Correo: {data['email']}\n"
                f"Teléfono: {data['phone'] or 'No indicado'}\n"
                f"Empresa o comunidad: {data['company'] or 'No indicada'}\n"
                f"Servicio: {data['service']}\n"
                f"Comuna: {data['commune'] or 'No indicada'}\n\n"
                f"Consulta:\n{data['message']}\n\n"
                f"Referencia: {data['request_id']}\n"
            ),
            from_email=sender,
            to=["contacto@inout.cl"],
            reply_to=[data["email"]],
        )
        try:
            sent = message.send(fail_silently=False)
        except Exception:
            _release_pending(redis_client, pending_key, token)
            raise
        if sent != 1:
            raise RuntimeError("Email transport did not accept the request.")

        if redis_client is not None:
            redis_client.set(sent_key, fingerprint, ex=IDEMPOTENCY_SECONDS)
        else:
            cache.set(sent_key, fingerprint, timeout=IDEMPOTENCY_SECONDS)
        _release_pending(redis_client, pending_key, token)
        return _response(202, ok=True)
    except Exception:
        logger.exception("Commercial contact email could not be accepted.")
        return _response(503, ok=False, error="delivery_unconfirmed")
