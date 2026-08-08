"""
ASGI config for backend_inout project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend_inout.settings')

django_asgi_application = get_asgi_application()

from backend_inout.jwt_websocket import JwtWebSocketAuthMiddleware
from backend_inout.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    "http": django_asgi_application,
    "websocket": AllowedHostsOriginValidator(
        JwtWebSocketAuthMiddleware(URLRouter(websocket_urlpatterns))
    ),
})
