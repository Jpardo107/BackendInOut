from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import QueryDict
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from instalacion.models import Instalacion
from user.models import Cargo, Usuario
from .models import ImagenReporteInforme, ReporteInforme

from .views import _image_text_values, _validate_images


class ReportesImageValidationTests(SimpleTestCase):
    def test_validate_images_allows_more_than_eight_files(self):
        files = [
            SimpleUploadedFile(
                f"foto_{index}.jpg",
                b"image-bytes",
                content_type="image/jpeg",
            )
            for index in range(9)
        ]

        _validate_images(files)


class ReportesImageTextValuesTests(SimpleTestCase):
    def test_reads_repeated_formdata_values(self):
        data = QueryDict("", mutable=True)
        data.update({"descripciones": "foto uno"})
        data.appendlist("descripciones", "foto dos")

        values = _image_text_values(data, ("descripciones", "descripcionFoto"), 2)

        self.assertEqual(values, ["foto uno", "foto dos"])

    def test_reads_json_array_formdata_value(self):
        data = QueryDict("", mutable=True)
        data.appendlist("recomendacionesFoto", '["rec uno", "rec dos"]')

        values = _image_text_values(data, ("recomendacionesFoto", "recomendacionFoto"), 2)

        self.assertEqual(values, ["rec uno", "rec dos"])

    def test_reads_indexed_values(self):
        data = QueryDict("", mutable=True)
        data.update({"descripcionFoto[0]": "foto uno", "descripcionFoto[1]": "foto dos"})

        values = _image_text_values(data, ("descripciones", "descripcionFoto"), 2)

        self.assertEqual(values, ["foto uno", "foto dos"])


class ReporteTextosUpdateTests(TestCase):
    def setUp(self):
        cargo = Cargo.objects.create(nombre="Administrador")
        self.user = Usuario.objects.create_user(
            username="editor.reportes", password="test-pass", nombres="Editor", apellidos="Reportes",
            rut="18181818-1", email="editor.reportes@example.com", cargo=cargo,
        )
        self.instalacion = Instalacion.objects.create(
            nombre="INSTALACION ORIGINAL", direccion="Dirección 1", comuna="Santiago",
            nombre_contacto="Contacto", correo_contacto="contacto@example.com", telefono_contacto="123456789",
        )
        self.reporte = ReporteInforme.objects.create(
            tipo_reporte=ReporteInforme.TIPO_PRE_INFORME, instalacion=self.instalacion,
            usuario_creador=self.user, autor_nombre="Editor Reportes", descripcion_hechos="Texto original",
            fecha_emision="2026-07-12",
        )
        self.imagen = ImagenReporteInforme.objects.create(
            reporte=self.reporte, storage_key="reportes/test/foto.jpg", nombre_original="foto.jpg",
            descripcion="Descripción original", orden=0,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_edita_textos_del_reporte_y_fotografia(self):
        response = self.client.patch(
            f"/api/reportes-informes/{self.reporte.id}/editar-textos/",
            {"descripcion_hechos": "Texto corregido", "imagenes": [{"id": self.imagen.id, "descripcion": "Foto corregida"}]},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.reporte.refresh_from_db()
        self.imagen.refresh_from_db()
        self.assertEqual(self.reporte.descripcion_hechos, "Texto corregido")
        self.assertEqual(self.imagen.descripcion, "Foto corregida")
        self.assertEqual(self.reporte.instalacion, self.instalacion)

    def test_preinforme_rechaza_campos_exclusivos_de_vulnerabilidades(self):
        response = self.client.patch(
            f"/api/reportes-informes/{self.reporte.id}/editar-textos/",
            {
                "analisis_final_usuario": "No corresponde al preinforme",
                "imagenes": [{"id": self.imagen.id, "recomendacion_usuario": "No corresponde"}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.reporte.refresh_from_db()
        self.imagen.refresh_from_db()
        self.assertEqual(self.reporte.analisis_final_usuario, "")
        self.assertEqual(self.imagen.recomendacion_usuario, "")
