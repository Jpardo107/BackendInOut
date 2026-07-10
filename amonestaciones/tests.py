from django.test import SimpleTestCase

from .services.openai_service import seleccionar_contexto_relevante


class SeleccionContextoTests(SimpleTestCase):
    def test_limita_documento_extenso_y_prioriza_fragmentos_relevantes(self):
        irrelevante = "Contenido administrativo general sin relación. " * 2500
        relevante = (
            "ARTÍCULO 25. TÍTULO OBLIGACIONES. El trabajador debe realizar las rondas de seguridad "
            "y registrar oportunamente cada control."
        )
        documento = f"{irrelevante}\n\n{relevante}\n\n{irrelevante}"

        resultado = seleccionar_contexto_relevante(
            documento,
            "El guardia omitió realizar y registrar una ronda de seguridad",
            max_chars=12000,
        )

        self.assertLessEqual(len(resultado), 12100)
        self.assertIn("ARTÍCULO 25", resultado)

    def test_documento_breve_se_conserva(self):
        documento = "CLÁUSULA 4. Obligación de puntualidad."
        self.assertEqual(
            seleccionar_contexto_relevante(documento, "atraso e impuntualidad"),
            documento,
        )
