import logging

from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.db import close_old_connections
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError


logger = logging.getLogger(__name__)


def _token_from_scope(scope):
    authorization = dict(scope.get("headers", [])).get(b"authorization", b"").decode("latin1")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()

    protocols = scope.get("subprotocols", [])
    try:
        marker = protocols.index("access_token")
        return protocols[marker + 1] if marker + 1 < len(protocols) else ""
    except ValueError:
        return ""


@database_sync_to_async
def _authenticate(raw_token):
    close_old_connections()
    if not raw_token:
        return AnonymousUser()

    authentication = JWTAuthentication()
    try:
        validated_token = authentication.get_validated_token(raw_token)
        user = authentication.get_user(validated_token)
        if not user.is_active:
            return AnonymousUser()
        return type(user).objects.select_related("cargo").get(pk=user.pk)
    except (InvalidToken, TokenError):
        return AnonymousUser()
    except Exception:
        logger.exception("Error autenticando conexión WebSocket JWT")
        return AnonymousUser()
    finally:
        close_old_connections()


class JwtWebSocketAuthMiddleware:
    """Reutiliza SimpleJWT sin exponer el access token en la URL."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        scope = dict(scope)
        scope["user"] = await _authenticate(_token_from_scope(scope))
        return await self.app(scope, receive, send)
