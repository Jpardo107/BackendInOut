import io
import zipfile
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from documentacion.models import DocumentoInstalacion
from instalacion.models import Instalacion
from user.models import Usuario


class DocumentosInstalacionZipTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = Usuario.objects.create_user(
            username="supervisor",
            password="password",
            nombres="Super",
            apellidos="Visor",
            rut="11111111-1",
            email="supervisor@example.com",
        )
        self.client.force_authenticate(user=self.user)
        self.instalacion = Instalacion.objects.create(
            nombre="Central / Norte",
            direccion="Av. Siempre Viva 123",
            comuna="Santiago",
            nombre_contacto="Contacto",
            correo_contacto="contacto@example.com",
            telefono_contacto="+56912345678",
        )

    def test_descarga_zip_con_documentos(self):
        DocumentoInstalacion.objects.create(
            instalacion=self.instalacion,
            titulo="Contrato",
            categoria="Legal",
            storage_key="documentos/contrato.pdf",
            nombre_original='contrato:final?.pdf',
            mime_type="application/pdf",
        )
        DocumentoInstalacion.objects.create(
            instalacion=self.instalacion,
            titulo="Plano",
            categoria="Tecnico",
            storage_key="documentos/plano.pdf",
            nombre_original="contrato:final?.pdf",
            mime_type="application/pdf",
        )

        def fake_download(key, fileobj):
            fileobj.write(f"contenido {key}".encode("utf-8"))

        with patch("documentacion.views.download_document_to_fileobj", side_effect=fake_download):
            response = self.client.get(
                f"/api/documentacion/instalaciones/{self.instalacion.id}/documentos/zip/"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")
        self.assertEqual(
            response["Content-Disposition"],
            'attachment; filename="Documentacion_Central Norte.zip"',
        )

        zip_file = zipfile.ZipFile(io.BytesIO(response.content))
        self.assertEqual(zip_file.namelist(), ["contratofinal.pdf", "contratofinal (2).pdf"])
        self.assertEqual(zip_file.read("contratofinal.pdf"), b"contenido documentos/contrato.pdf")

    def test_responde_404_si_no_hay_documentos(self):
        response = self.client.get(
            f"/api/documentacion/instalaciones/{self.instalacion.id}/documentos/zip/"
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(),
            {"detail": "La instalación no tiene documentos para descargar."},
        )

    def test_omite_documentos_fallidos_si_al_menos_uno_descarga(self):
        DocumentoInstalacion.objects.create(
            instalacion=self.instalacion,
            titulo="Existe",
            categoria="Legal",
            storage_key="documentos/existe.pdf",
            nombre_original="existe.pdf",
        )
        DocumentoInstalacion.objects.create(
            instalacion=self.instalacion,
            titulo="Falta",
            categoria="Legal",
            storage_key="documentos/falta.pdf",
            nombre_original="falta.pdf",
        )

        def fake_download(key, fileobj):
            if key.endswith("falta.pdf"):
                raise FileNotFoundError(key)
            fileobj.write(b"ok")

        with patch("documentacion.views.download_document_to_fileobj", side_effect=fake_download):
            response = self.client.get(
                f"/api/documentacion/instalaciones/{self.instalacion.id}/documentos/zip/"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Skipped-Documents"], "1")
        zip_file = zipfile.ZipFile(io.BytesIO(response.content))
        self.assertEqual(zip_file.namelist(), ["existe.pdf"])

    def test_responde_error_si_todos_los_documentos_fallan(self):
        DocumentoInstalacion.objects.create(
            instalacion=self.instalacion,
            titulo="Falta",
            categoria="Legal",
            storage_key="documentos/falta.pdf",
            nombre_original="falta.pdf",
        )

        with patch(
            "documentacion.views.download_document_to_fileobj",
            side_effect=FileNotFoundError("no existe"),
        ):
            response = self.client.get(
                f"/api/documentacion/instalaciones/{self.instalacion.id}/documentos/zip/"
            )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json(),
            {"detail": "No se pudo descargar ningún archivo de la instalación desde el storage."},
        )
