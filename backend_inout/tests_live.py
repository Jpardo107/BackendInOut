import json

from asgiref.sync import sync_to_async
from asgiref.testing import ApplicationCommunicator
from django.test import TransactionTestCase, override_settings
from rest_framework_simplejwt.tokens import AccessToken

from backend_inout.asgi import application
from backend_inout.live_events import schedule_live_event
from user.models import Cargo, Usuario


@override_settings(CHANNEL_LAYERS={
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
})
class LiveWebSocketTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        admin_role = Cargo.objects.create(nombre="Administrador")
        supervisor_role = Cargo.objects.create(nombre="Supervisor")
        self.admin = Usuario.objects.create_user(
            username="live.admin", password="test-pass", nombres="Admin", apellidos="Live",
            rut="15555555-5", email="live.admin@example.com", cargo=admin_role,
        )
        self.supervisor = Usuario.objects.create_user(
            username="live.supervisor", password="test-pass", nombres="Supervisor", apellidos="Live",
            rut="16666666-6", email="live.supervisor@example.com", cargo=supervisor_role,
        )

    def communicator(self, subprotocols=None):
        return ApplicationCommunicator(application, {
            "type": "websocket",
            "path": "/ws/vistas-en-vivo/",
            "raw_path": b"/ws/vistas-en-vivo/",
            "query_string": b"",
            "headers": [],
            "subprotocols": subprotocols or [],
        })

    async def connect(self, communicator):
        await communicator.send_input({"type": "websocket.connect"})
        return await communicator.receive_output(timeout=1)

    async def test_rechaza_conexion_anonima(self):
        communicator = self.communicator()
        response = await self.connect(communicator)
        self.assertEqual(response, {"type": "websocket.close", "code": 4401})

    async def test_rechaza_cargo_supervisor(self):
        token = str(AccessToken.for_user(self.supervisor))
        communicator = self.communicator(["access_token", token])
        response = await self.connect(communicator)
        self.assertEqual(response, {"type": "websocket.close", "code": 4403})

    async def test_admin_autenticado_recibe_evento_resumido(self):
        token = str(AccessToken.for_user(self.admin))
        communicator = self.communicator(["access_token", token])
        response = await self.connect(communicator)
        self.assertEqual(response, {"type": "websocket.accept", "subprotocol": "access_token"})

        await sync_to_async(schedule_live_event, thread_sensitive=True)(
            "supervision.started", {"id": 77, "estado": "iniciada"}
        )
        output = await communicator.receive_output(timeout=1)
        message = json.loads(output["text"])
        self.assertEqual(message, {
            "type": "supervision.started",
            "data": {"id": 77, "estado": "iniciada"},
        })
        await communicator.send_input({"type": "websocket.disconnect", "code": 1000})
        await communicator.wait(timeout=1)
