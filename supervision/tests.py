from datetime import date, time
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from instalacion.models import Instalacion
from user.models import Cargo, Usuario
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
        completed = publish_mock.call_args_list[1].args[1]
        self.assertEqual(completed["novedades"], "Sin novedades")
        self.assertEqual(completed["solicitudes"], "Reponer extintor")


class SupervisionStartTests(TestCase):
    def setUp(self):
        cargo = Cargo.objects.create(nombre="Supervisor")
        self.supervisor = Usuario.objects.create_user(
            username="supervisor.qr",
            password="test-pass",
            nombres="Ana",
            apellidos="Pérez",
            rut="17777777-7",
            email="supervisor.qr@example.com",
            cargo=cargo,
        )
        self.instalacion = Instalacion.objects.create(
            nombre="Planta Norte",
            direccion="Ruta 5",
            comuna="Lampa",
            nombre_contacto="Contacto",
            correo_contacto="contacto@example.com",
            telefono_contacto="+56911111111",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.supervisor)

    @patch("supervision.views.schedule_live_event")
    def test_escaneo_registra_evento_de_inicio_con_usuario_autenticado(self, publish_mock):
        response = self.client.post(
            "/api/supervision/supervisiones/iniciar/",
            {"instalacion": self.instalacion.id},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["instalacion"], "Planta Norte")
        self.assertEqual(response.data["supervisor"], "Ana Pérez")
        publish_mock.assert_called_once()
        self.assertEqual(publish_mock.call_args.args[0], "supervision.started")

    def test_inicio_rechaza_instalacion_inexistente(self):
        response = self.client.post(
            "/api/supervision/supervisiones/iniciar/",
            {"instalacion": 999999},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
