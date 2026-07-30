from django.test import TestCase
from rest_framework.test import APIClient

from instalacion.models import Instalacion, Zona
from .models import Cargo, PersonalEmpresa, Usuario
from .serializers import PersonalEmpresaSerializer
from .services.instalacion_matcher import buscar_instalacion, construir_indice_instalaciones
from .services.rut import formatear_rut, normalizar_rut


class RutTests(TestCase):
    def test_normaliza_rut_sin_puntos_ni_guion(self):
        self.assertEqual(normalizar_rut("18.935.687-0"), "189356870")
        self.assertEqual(normalizar_rut("8.801.779-K"), "8801779K")
        self.assertEqual(normalizar_rut("130562361"), "130562361")

    def test_formatea_rut_para_ui(self):
        self.assertEqual(formatear_rut("189356870"), "18.935.687-0")
        self.assertEqual(formatear_rut("8801779K"), "8.801.779-K")


class SupervisorListTests(TestCase):
    def test_incluye_supervisores_y_coordinadores_de_operaciones(self):
        cargo_rrhh = Cargo.objects.create(nombre="Encargado RRHH")
        cargo_supervisor = Cargo.objects.create(nombre="Supervisor")
        cargo_coordinador = Cargo.objects.create(nombre="Coordinador de Operaciones")
        rrhh = Usuario.objects.create_user(
            username="rrhh.lista",
            password="test-pass",
            nombres="RRHH",
            apellidos="Lista",
            rut="11111111-1",
            email="rrhh.lista@example.com",
            cargo=cargo_rrhh,
        )
        supervisor = Usuario.objects.create_user(
            username="supervisor.lista",
            password="test-pass",
            nombres="Supervisor",
            apellidos="Lista",
            rut="22222222-2",
            email="supervisor.lista@example.com",
            cargo=cargo_supervisor,
        )
        coordinador = Usuario.objects.create_user(
            username="coordinador.lista",
            password="test-pass",
            nombres="Coordinador",
            apellidos="Lista",
            rut="33333333-3",
            email="coordinador.lista@example.com",
            cargo=cargo_coordinador,
        )

        client = APIClient()
        client.force_authenticate(user=rrhh)
        response = client.get("/api/supervisores/")

        self.assertEqual(response.status_code, 200)
        ids = {item["id"] for item in response.data}
        self.assertEqual(ids, {supervisor.id, coordinador.id})


class PersonalEmpresaTests(TestCase):
    def test_rut_es_unico_normalizado(self):
        PersonalEmpresa.objects.create(
            rut=normalizar_rut("18.935.687-0"),
            nombre_completo="CESPEDES VARGAS MARCELO JAVIER",
            ubicacion="BODEGA SAN JOAQUIN",
        )

        self.assertTrue(PersonalEmpresa.objects.filter(rut="189356870").exists())

    def test_persona_nueva_exige_instalacion(self):
        serializer = PersonalEmpresaSerializer(data={
            "rut": "18.935.687-0",
            "nombre_completo": "Persona Nueva",
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn("instalacion", serializer.errors)

    def test_persona_nueva_toma_ubicacion_desde_instalacion(self):
        Zona.objects.get_or_create(codigo="centro", defaults={"nombre": "Centro"})
        instalacion = Instalacion.objects.create(
            nombre="Edificio Central",
            direccion="Calle 1",
            comuna="Santiago",
            nombre_contacto="Contacto",
            correo_contacto="contacto@example.com",
            telefono_contacto="123",
            zona="centro",
        )
        serializer = PersonalEmpresaSerializer(data={
            "rut": "18.935.687-0",
            "nombre_completo": "Persona Nueva",
            "instalacion": instalacion.id,
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        persona = serializer.save()
        self.assertEqual(persona.instalacion, instalacion)
        self.assertEqual(persona.ubicacion, "EDIFICIO CENTRAL")

    def test_busca_instalacion_por_nombre_normalizado_y_alias(self):
        instalacion = Instalacion.objects.create(
            nombre="Logisfashion Miraflores",
            direccion="Dirección",
            comuna="Santiago",
            nombre_contacto="Contacto",
            correo_contacto="contacto@example.com",
            telefono_contacto="123456789",
        )
        indice = construir_indice_instalaciones()

        self.assertEqual(buscar_instalacion("LOGIS MIRAFLORES", indice), instalacion)

    def test_no_elige_instalacion_si_el_nombre_es_ambiguo(self):
        datos = {
            "nombre": "Bodega",
            "direccion": "Dirección",
            "comuna": "Santiago",
            "nombre_contacto": "Contacto",
            "correo_contacto": "contacto@example.com",
            "telefono_contacto": "123456789",
        }
        Instalacion.objects.create(**datos)
        Instalacion.objects.create(**datos)

        self.assertIsNone(buscar_instalacion("BODEGA", construir_indice_instalaciones()))
