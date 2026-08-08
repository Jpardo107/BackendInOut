from datetime import date, time
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from .views import SupervisionViewSet


class SupervisionLiveEventTests(SimpleTestCase):
    @patch("supervision.views.schedule_live_event")
    def test_crear_supervision_programa_eventos_resumidos(self, publish_mock):
        supervision = SimpleNamespace(
            id=91,
            instalacion_id=12,
            instalacion=SimpleNamespace(nombre="PLANTA EVENTOS"),
            supervisor_id=7,
            supervisor=SimpleNamespace(nombres="Sara", apellidos="Soto"),
            fecha=date(2026, 8, 8),
            hora_inicio=time(10, 0),
            hora_final=time(10, 30),
            novedades="Sin novedades",
            solicitudes="Reponer extintor",
            estado_solicitud="pendiente",
        )
        serializer = Mock()
        serializer.save.return_value = supervision

        SupervisionViewSet().perform_create(serializer)

        event_types = [call.args[0] for call in publish_mock.call_args_list]
        self.assertEqual(event_types, [
            "supervision.created", "supervision.completed", "solicitud.created"
        ])
        self.assertEqual(publish_mock.call_args_list[0].args[1]["id"], 91)
