from django.test import TestCase
from rest_framework.test import APIClient

from user.models import Cargo, Usuario
from .models import Instalacion, Zona


class ZonaApiTests(TestCase):
    def setUp(self):
        cargo = Cargo.objects.create(nombre="Administrador")
        self.usuario = Usuario.objects.create_user(
            username="admin.zonas", password="test-pass", nombres="Admin",
            apellidos="Zonas", rut="19999999-9", email="zonas@example.com",
            cargo=cargo, is_staff=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.usuario)
        self.zona = Zona.objects.get(codigo="centro")

    def crear_instalacion(self, zona="centro"):
        return Instalacion.objects.create(
            nombre="Instalación Test", direccion="Dirección 1", comuna="Santiago",
            nombre_contacto="Contacto", correo_contacto="contacto@example.com",
            telefono_contacto="123456789", zona=zona,
        )

    def test_crea_zona(self):
        response = self.client.post("/api/zonas/", {"codigo": "costa", "nombre": "Costa"}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Zona.objects.filter(codigo="costa", nombre="Costa").exists())

    def test_editar_codigo_actualiza_instalaciones(self):
        instalacion = self.crear_instalacion()
        response = self.client.patch(
            f"/api/zonas/{self.zona.id}/", {"codigo": "centro-sur", "nombre": "Centro Sur"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        instalacion.refresh_from_db()
        self.assertEqual(instalacion.zona, "centro-sur")

    def test_no_elimina_zona_asignada(self):
        self.crear_instalacion()
        response = self.client.delete(f"/api/zonas/{self.zona.id}/")
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Zona.objects.filter(pk=self.zona.id).exists())

    def test_elimina_zona_sin_instalaciones(self):
        response = self.client.delete(f"/api/zonas/{self.zona.id}/")
        self.assertEqual(response.status_code, 204)

    def test_instalacion_rechaza_zona_inexistente(self):
        payload = {
            "nombre": "Instalación API", "direccion": "Dirección 2", "comuna": "Santiago",
            "nombre_contacto": "Contacto", "correo_contacto": "contacto@example.com",
            "telefono_contacto": "123456789", "zona": "fantasma",
        }
        response = self.client.post("/api/instalaciones/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("zona", response.data)
