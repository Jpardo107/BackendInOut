from django.test import SimpleTestCase
from types import SimpleNamespace
from zipfile import ZipFile

from .services.openai_service import seleccionar_contexto_relevante
from .services.word_service import generar_word_amonestacion


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


class WordAmonestacionTests(SimpleTestCase):
    def test_genera_docx_valido_con_contenido_y_firmas(self):
        amonestacion = SimpleNamespace(
            carta="Santiago, 10 de julio de 2026\n\nSEÑOR\nJUAN PÉREZ\n\nDe nuestra consideración:\n\nCarta breve.",
            persona=SimpleNamespace(nombre_completo="Juan Pérez", rut="12345678-9"),
        )

        archivo = generar_word_amonestacion(amonestacion)

        with ZipFile(archivo) as docx:
            contenido = docx.read("word/document.xml").decode("utf-8")
        self.assertIn("Carta breve.", contenido)
        self.assertIn("INOUT SEGURIDAD SpA", contenido)
        self.assertIn("JUAN PÉREZ", contenido)
