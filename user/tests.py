from django.test import TestCase

from instalacion.models import Instalacion, Zona
from .models import PersonalEmpresa
from .serializers import PersonalEmpresaSerializer
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
