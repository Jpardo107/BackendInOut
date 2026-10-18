from django.test import override_settings
from rest_framework.test import APITestCase
from instalacion.models import Instalacion
from .models import PersonalEmpresa


@override_settings(RONDAPP_INTEGRATION_KEY="integration-test-key")
class GuardiaLookupTests(APITestCase):
    def setUp(self):
        self.installation = Instalacion.objects.create(nombre="MAFORSA", direccion="Prueba", comuna="Santiago", nombre_contacto="Contacto", correo_contacto="qa@example.com", telefono_contacto="123")
        self.guard = PersonalEmpresa.objects.create(rut="123456785", nombre_completo="ANA PEREZ SOTO", instalacion=self.installation)
        self.url = "/api/integraciones/rondas/guardia/"

    def lookup(self, rut="12.345.678-5", key="integration-test-key"):
        return self.client.post(self.url, {"rut": rut}, format="json", HTTP_X_RONDAPP_KEY=key)

    def test_only_private_service_can_lookup(self):
        self.assertEqual(self.lookup(key="").status_code, 403)
        self.assertEqual(self.lookup(key="incorrect").status_code, 403)
        self.assertEqual(self.client.get(self.url, HTTP_X_RONDAPP_KEY="integration-test-key").status_code, 405)

    def test_returns_minimum_identity_and_assigned_installation(self):
        response = self.lookup()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"id": self.guard.id, "rut": "123456785", "nombre": "ANA PEREZ SOTO", "instalacion": {"id": self.installation.id, "nombre": "MAFORSA"}})
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_inactive_unassigned_unknown_or_ambiguous_guard_rejected(self):
        self.assertEqual(self.lookup("11111111-1").status_code, 404)
        self.guard.activo = False
        self.guard.save()
        self.assertEqual(self.lookup().status_code, 403)
        self.guard.activo = True
        self.guard.instalacion = None
        self.guard.save()
        self.assertEqual(self.lookup().status_code, 409)
        PersonalEmpresa.objects.create(rut="12.345.678-5", nombre_completo="Duplicado", instalacion=self.installation)
        self.assertEqual(self.lookup().status_code, 404)

    @override_settings(RONDAPP_INTEGRATION_KEY="")
    def test_empty_server_key_never_grants_access(self):
        self.assertEqual(self.lookup(key="").status_code, 403)
