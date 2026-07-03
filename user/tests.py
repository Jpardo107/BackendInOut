from django.test import TestCase

from .models import PersonalEmpresa
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
