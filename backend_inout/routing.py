from django.urls import path

from backend_inout.consumers import LiveViewsConsumer


websocket_urlpatterns = [
    path("ws/vistas-en-vivo/", LiveViewsConsumer.as_asgi()),
]
