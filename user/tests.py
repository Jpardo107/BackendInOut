from django.test import TestCase

from instalacion.models import Instalacion, Zona
from .models import PersonalEmpresa
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
