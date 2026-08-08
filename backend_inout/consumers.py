import logging

from channels.generic.websocket import AsyncJsonWebsocketConsumer

from backend_inout.live_events import can_access_live, live_group_name


logger = logging.getLogger(__name__)


class LiveViewsConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            logger.info("Conexión WebSocket en vivo rechazada: usuario anónimo")
            await self.close(code=4401)
            return
        if not can_access_live(user):
            logger.info("Conexión WebSocket en vivo rechazada por permisos user_id=%s", user.pk)
            await self.close(code=4403)
            return

        self.live_group = live_group_name(user=user)
        try:
            await self.channel_layer.group_add(self.live_group, self.channel_name)
        except Exception:
            logger.exception("No fue posible unir conexión WebSocket al grupo %s", self.live_group)
            await self.close(code=1013)
            return
        protocols = self.scope.get("subprotocols", [])
        subprotocol = "access_token" if "access_token" in protocols else None
        await self.accept(subprotocol=subprotocol)
        logger.info("WebSocket en vivo conectado user_id=%s group=%s", user.pk, self.live_group)

    async def disconnect(self, close_code):
        group = getattr(self, "live_group", None)
        if group:
            await self.channel_layer.group_discard(group, self.channel_name)
            user = self.scope.get("user")
            logger.info(
                "WebSocket en vivo desconectado user_id=%s group=%s code=%s",
                getattr(user, "pk", None), group, close_code,
            )

    async def receive_json(self, content, **kwargs):
        if content.get("type") == "ping":
            await self.send_json({"type": "pong"})

    async def live_event(self, event):
        await self.send_json(event["event"])
