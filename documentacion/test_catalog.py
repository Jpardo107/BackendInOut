import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from documentacion.models import DocumentoInstalacion, TipoDocumentoInstalacion, DocumentoItem
from instalacion.models import Instalacion
from user.models import Usuario

BASE = "/api/documentacion/"


class CatalogFixtures(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create_user(username="catalog-admin", password="test", rut="19999999-9", email="admin@example.com", is_staff=True)
        self.reader = Usuario.objects.create_user(username="catalog-reader", password="test", rut="18888888-8", email="reader@example.com")
        self.client = APIClient(); self.client.force_authenticate(self.admin)
        self.site = Instalacion.objects.create(nombre="Instalación QA", direccion="QA", comuna="QA", nombre_contacto="QA", correo_contacto="qa@example.com", telefono_contacto="123")
        self.tipo = TipoDocumentoInstalacion.objects.create(nombre="Protocolo", orden=1)

    def upload(self, tipo=None):
        return self.client.post(f"{BASE}instalaciones/{self.site.id}/documentos/", {
            "file": SimpleUploadedFile("prueba.pdf", b"%PDF-1.4 test", content_type="application/pdf"),
            "titulo": "Protocolo QA", "categoria": tipo or self.tipo.codigo,
        }, format="multipart")


class CatalogTests(CatalogFixtures):
    def test_catalog_crud_normalizes_and_rejects_duplicate_names(self):
        url = BASE + "tipos-instalacion/"
        result = self.client.post(url, {"nombre": "  Plan   de emergencia  ", "orden": 2})
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(result.data["nombre"], "Plan de emergencia")
        self.assertEqual(self.client.post(url, {"nombre": "plan de emergencia"}).status_code, 400)
        self.assertEqual(self.client.post(url, {"nombre": "  "}).status_code, 400)
        id, code = result.data["id"], result.data["codigo"]
        edit = self.client.patch(f"{url}{id}/", {"nombre": "Instructivo", "codigo": "otro", "orden": 0})
        self.assertEqual(edit.status_code, 200)
        self.assertEqual(edit.data["codigo"], code)
        self.assertEqual(self.client.get(url).data[0]["nombre"], "Instructivo")
        self.assertEqual(self.client.delete(f"{url}{id}/").status_code, 204)

    def test_only_administration_changes_catalog(self):
        self.client.force_authenticate(self.reader)
        self.assertEqual(self.client.get(BASE + "tipos-instalacion/").status_code, 200)
        self.assertEqual(self.client.post(BASE + "tipos-instalacion/", {"nombre":"Plan"}).status_code, 403)
        self.assertEqual(self.client.patch(f"{BASE}tipos-instalacion/{self.tipo.pk}/", {"nombre":"Plan"}).status_code, 403)
        self.assertEqual(self.client.delete(f"{BASE}tipos-instalacion/{self.tipo.pk}/").status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(BASE + "tipos-instalacion/").status_code, 401)

    @patch("documentacion.views.upload_document")
    def test_upload_tracks_type_rename_and_duplicate(self, upload):
        response = self.upload()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.upload().status_code, 409)
        self.assertEqual(upload.call_count, 1)
        doc = DocumentoInstalacion.objects.get()
        self.assertEqual(doc.tipo_documento, self.tipo)
        self.client.patch(f"{BASE}tipos-instalacion/{self.tipo.pk}/", {"nombre":"Nuevo nombre"})
        doc.refresh_from_db(); self.assertEqual(doc.categoria,self.tipo.codigo)
        self.assertEqual(self.client.get(BASE + "tipos-instalacion/").data[0]["documentos_subidos"], 1)
        self.assertEqual(self.client.delete(f"{BASE}tipos-instalacion/{self.tipo.pk}/").status_code, 400)

    @patch("documentacion.views.upload_document")
    def test_rejects_removed_or_unconfigured_type_before_upload(self, upload):
        self.assertEqual(self.upload("directiva").status_code, 400)
        code=self.tipo.codigo;self.tipo.delete()
        self.assertEqual(self.upload(code).status_code, 400)
        upload.assert_not_called()

    @patch("documentacion.views.delete_document")
    @patch("documentacion.views.upload_document")
    def test_replace_and_delete_original_and_preview(self, upload, delete):
        self.upload();doc=DocumentoInstalacion.objects.get();old=doc.storage_key
        response=self.client.put(f"{BASE}instalaciones/{self.site.pk}/documentos/{doc.pk}/replace/",{
            "file":SimpleUploadedFile("nuevo.pdf",b"pdf"),"titulo":"Nuevo","categoria":self.tipo.codigo},format="multipart")
        self.assertEqual(response.status_code,200,response.data)
        doc.refresh_from_db();self.assertNotEqual(old,doc.storage_key)
        delete.assert_any_call(old)
        self.client.force_authenticate(self.reader)
        self.assertEqual(self.client.delete(f"{BASE}documentos/{doc.pk}/").status_code,403)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.delete(f"{BASE}documentos/{doc.pk}/").status_code,204)
        delete.assert_any_call(doc.storage_key)
        delete.assert_any_call(f"documentos/previews/instalacion_{self.site.pk}/documento_{doc.pk}.pdf")
        self.assertFalse(DocumentoInstalacion.objects.exists())
        self.assertEqual(self.client.delete(f"{BASE}tipos-instalacion/{self.tipo.pk}/").status_code,204)

    @patch("documentacion.views.delete_document", side_effect=RuntimeError("storage unavailable"))
    def test_delete_storage_failure_retains_record(self, delete):
        doc=DocumentoInstalacion.objects.create(instalacion=self.site,tipo_documento=self.tipo,titulo="QA",storage_key=f"documentos/instalacion_{self.site.pk}/test.pdf")
        self.assertEqual(self.client.delete(f"{BASE}documentos/{doc.pk}/").status_code,502)
        self.assertTrue(DocumentoInstalacion.objects.filter(pk=doc.pk).exists())


class ResetTests(CatalogFixtures):
    def prepare_storage(self):
        doc = DocumentoInstalacion.objects.create(instalacion=self.site,tipo_documento=self.tipo,titulo="QA",categoria=self.tipo.codigo,storage_key=f"documentos/instalacion_{self.site.pk}/old.pdf")
        self.other_item=DocumentoItem.objects.create(nombre="Lista de supervisión")
        self.objects={doc.storage_key:10, f"documentos/previews/instalacion_{self.site.pk}/documento_{doc.pk}.pdf":5,
            "documentos/instalacion_999/orphan.pdf":3, "documentos/amonestaciones/contrato/test.pdf":9}
        client=MagicMock()
        client.get_paginator.return_value.paginate.side_effect=lambda **kw: [{"Contents":[{"Key":k,"Size":size} for k,size in self.objects.items() if k.startswith(kw["Prefix"])]}]
        def delete(**kw): self.objects.pop(kw["Key"],None);return {}
        client.delete_object.side_effect=delete
        def batch(**kw):
            for obj in kw["Delete"]["Objects"]: self.objects.pop(obj["Key"],None)
            return {}
        client.delete_objects.side_effect=batch
        return doc,client

    def test_dry_run_never_deletes(self):
        doc,client=self.prepare_storage()
        with patch("documentacion.management.commands.reiniciar_documentacion_instalaciones.get_r2_client",return_value=client):
            call_command("reiniciar_documentacion_instalaciones",stdout=io.StringIO())
        client.delete_object.assert_not_called();client.delete_objects.assert_not_called()
        self.assertTrue(DocumentoInstalacion.objects.filter(pk=doc.pk).exists())

    def test_reset_deletes_only_installation_scope_and_empty_catalog(self):
        doc,client=self.prepare_storage()
        with tempfile.TemporaryDirectory() as temp, patch("documentacion.management.commands.reiniciar_documentacion_instalaciones.get_r2_client",return_value=client):
            manifest=Path(temp)/"reset.json"
            call_command("reiniciar_documentacion_instalaciones",execute=True,confirm="REINICIAR_DOCUMENTACION_INSTALACIONES",allow_sqlite=True,manifest=str(manifest),stdout=io.StringIO())
            self.assertEqual(len(json.loads(manifest.read_text())["documents"]),1)
        self.assertFalse(DocumentoInstalacion.objects.exists());self.assertFalse(TipoDocumentoInstalacion.objects.exists())
        self.assertEqual(list(self.objects),["documentos/amonestaciones/contrato/test.pdf"])
        self.assertTrue(DocumentoItem.objects.filter(pk=self.other_item.pk).exists())

    def test_partial_failure_retains_failed_document_and_catalog_for_retry(self):
        doc,client=self.prepare_storage();client.delete_object.side_effect=RuntimeError("R2 failure")
        with tempfile.TemporaryDirectory() as temp, patch("documentacion.management.commands.reiniciar_documentacion_instalaciones.get_r2_client",return_value=client):
            with self.assertRaises(CommandError):
                call_command("reiniciar_documentacion_instalaciones",execute=True,confirm="REINICIAR_DOCUMENTACION_INSTALACIONES",allow_sqlite=True,manifest=str(Path(temp)/"reset.json"),stdout=io.StringIO())
        self.assertTrue(DocumentoInstalacion.objects.filter(pk=doc.pk).exists());self.assertTrue(TipoDocumentoInstalacion.objects.exists())
        self.assertIn(doc.storage_key,self.objects)

    def test_execute_refuses_default_local_database_and_missing_confirmation(self):
        with self.assertRaises(CommandError): call_command("reiniciar_documentacion_instalaciones",execute=True)
        with self.assertRaises(CommandError): call_command("reiniciar_documentacion_instalaciones",execute=True,confirm="REINICIAR_DOCUMENTACION_INSTALACIONES")

    def test_orphan_delete_error_does_not_claim_clean_or_remove_catalog(self):
        doc,client=self.prepare_storage()
        client.delete_objects.side_effect=None
        client.delete_objects.return_value={"Errors":[{"Key":"documentos/instalacion_999/orphan.pdf","Code":"AccessDenied"}]}
        with tempfile.TemporaryDirectory() as temp, patch("documentacion.management.commands.reiniciar_documentacion_instalaciones.get_r2_client",return_value=client):
            with self.assertRaises(CommandError):
                call_command("reiniciar_documentacion_instalaciones",execute=True,confirm="REINICIAR_DOCUMENTACION_INSTALACIONES",allow_sqlite=True,manifest=str(Path(temp)/"reset.json"),stdout=io.StringIO())
        self.assertFalse(DocumentoInstalacion.objects.exists())
        self.assertTrue(TipoDocumentoInstalacion.objects.exists())
        self.assertIn("documentos/instalacion_999/orphan.pdf",self.objects)

    def test_record_outside_module_scope_aborts_before_any_deletion(self):
        doc,client=self.prepare_storage()
        doc.storage_key="documentos/amonestaciones/contrato/test.pdf";doc.save()
        with tempfile.TemporaryDirectory() as temp, patch("documentacion.management.commands.reiniciar_documentacion_instalaciones.get_r2_client",return_value=client):
            with self.assertRaises(CommandError):
                call_command("reiniciar_documentacion_instalaciones",execute=True,confirm="REINICIAR_DOCUMENTACION_INSTALACIONES",allow_sqlite=True,manifest=str(Path(temp)/"reset.json"),stdout=io.StringIO())
        client.delete_object.assert_not_called();client.delete_objects.assert_not_called()
        self.assertTrue(DocumentoInstalacion.objects.filter(pk=doc.pk).exists())
