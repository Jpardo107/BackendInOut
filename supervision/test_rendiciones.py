from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image
from rest_framework.test import APIClient

from user.models import Cargo, Usuario
from .models import RendicionGasto


class RendicionGastoTests(TestCase):
    endpoint = "/api/supervision/rendiciones-gastos/"

    def setUp(self):
        cargo = Cargo.objects.create(nombre="Supervisor")
        self.supervisor = Usuario.objects.create_user(
            username="sup-gastos", nombres="Ana", apellidos="Pérez", rut="11111111-1",
            email="sup@example.test", cargo=cargo,
        )
        self.other = Usuario.objects.create_user(
            username="otro-gastos", nombres="Luis", apellidos="Soto", rut="22222222-2",
            email="otro@example.test", cargo=cargo,
        )
        self.admin = Usuario.objects.create_user(
            username="admin-gastos", rut="33333333-3", email="admin@example.test", is_staff=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.supervisor)

    def image(self):
        buffer = BytesIO()
        Image.new("RGB", (20, 20), "white").save(buffer, format="PNG")
        return SimpleUploadedFile("comprobante.png", buffer.getvalue(), content_type="image/png")

    def expense(self, supervisor=None, **values):
        user = supervisor or self.supervisor
        return RendicionGasto.objects.create(
            supervisor=user, supervisor_nombre=str(user), storage_key="rendiciones-gastos/test.png",
            instalacion=values.get("instalacion", "Planta Norte"), persona=values.get("persona", "Pedro Soto"),
        )

    @patch("supervision.rendiciones.upload_document")
    def test_create_records_authenticated_supervisor_and_server_time(self, upload):
        before = datetime.now(timezone.utc)
        response = self.client.post(self.endpoint, {
            "imagen": self.image(), "instalacion": "  Planta Norte  ", "persona": " Pedro Soto ",
            "supervisor": self.other.id, "supervisor_nombre": "Falso", "creada_en": "2000-01-01T00:00:00Z",
        }, format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        expense = RendicionGasto.objects.get()
        self.assertEqual(expense.supervisor, self.supervisor)
        self.assertEqual(expense.supervisor_nombre, "Ana Pérez")
        self.assertGreaterEqual(expense.creada_en, before)
        self.assertEqual(expense.instalacion, "Planta Norte")
        self.assertEqual(expense.persona, "Pedro Soto")
        self.assertTrue(expense.storage_key.startswith("rendiciones-gastos/"))
        upload.assert_called_once()

    @patch("supervision.rendiciones.upload_document")
    def test_all_fields_required_and_invalid_images_rejected(self, upload):
        payloads = [
            {"instalacion": "Planta", "persona": "Pedro"},
            {"imagen": self.image(), "instalacion": "  ", "persona": "Pedro"},
            {"imagen": self.image(), "instalacion": "Planta", "persona": "  "},
            {"imagen": SimpleUploadedFile("fake.png", b"invalid", content_type="image/png"), "instalacion": "Planta", "persona": "Pedro"},
        ]
        for payload in payloads:
            with self.subTest(fields=list(payload)):
                self.assertEqual(self.client.post(self.endpoint, payload, format="multipart").status_code, 400)
        self.assertFalse(RendicionGasto.objects.exists())
        upload.assert_not_called()

    @patch("supervision.rendiciones.upload_document")
    def test_oversized_image_rejected(self, upload):
        image = self.image()
        oversized = SimpleUploadedFile("large.png", image.read() + b"\0" * (10 * 1024 * 1024), content_type="image/png")
        response = self.client.post(self.endpoint, {"imagen": oversized, "instalacion": "Planta", "persona": "Pedro"}, format="multipart")
        self.assertEqual(response.status_code, 400)
        upload.assert_not_called()

    @patch("supervision.rendiciones.upload_document", side_effect=RuntimeError("Storage unavailable"))
    def test_storage_failure_does_not_create_expense(self, upload):
        with self.assertLogs("supervision.rendiciones", level="ERROR"):
            response = self.client.post(self.endpoint, {"imagen": self.image(), "instalacion": "Planta", "persona": "Pedro"}, format="multipart")
        self.assertEqual(response.status_code, 500)
        self.assertFalse(RendicionGasto.objects.exists())

    @patch("supervision.rendiciones.upload_document")
    @patch("supervision.rendiciones.delete_document")
    @patch("supervision.rendiciones.RendicionSerializer.save", side_effect=RuntimeError("DB failure"))
    def test_database_failure_cleans_uploaded_image(self, save, delete, upload):
        with self.assertRaises(RuntimeError):
            self.client.post(self.endpoint, {"imagen": self.image(), "instalacion": "Planta", "persona": "Pedro"}, format="multipart")
        delete.assert_called_once_with(upload.call_args.args[1])

    @patch("supervision.rendiciones.generate_signed_url", return_value="https://storage.test/comprobante")
    def test_supervisor_only_sees_own_expenses_and_images(self, sign):
        own = self.expense()
        other = self.expense(self.other)
        response = self.client.get(self.endpoint)
        self.assertEqual([row["id"] for row in response.data["results"]], [own.id])
        self.assertEqual(self.client.get(f"{self.endpoint}{other.id}/").status_code, 404)
        self.assertEqual(self.client.get(f"{self.endpoint}{other.id}/imagen/").status_code, 404)
        sign.assert_not_called()
        self.assertEqual(self.client.get(f"{self.endpoint}{own.id}/imagen/").status_code, 200)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(self.endpoint).data["count"], 2)
        self.assertEqual(self.client.get(f"{self.endpoint}{other.id}/imagen/").status_code, 200)

    def test_filters_individually_and_combined_with_chilean_dates(self):
        first = self.expense()
        second = self.expense(self.other, instalacion="Planta Sur", persona="María Díaz")
        # In September Chile is UTC-3: 02:59 UTC belongs to the previous local day.
        RendicionGasto.objects.filter(pk=first.pk).update(creada_en=datetime(2026, 9, 25, 2, 59, tzinfo=timezone.utc))
        RendicionGasto.objects.filter(pk=second.pk).update(creada_en=datetime(2026, 9, 25, 3, 0, tzinfo=timezone.utc))
        self.client.force_authenticate(self.admin)
        for filters in [
            {"supervisor": self.supervisor.id}, {"instalacion": "norte"}, {"persona": "Pedro"},
            {"fecha_desde": "2026-09-24", "fecha_hasta": "2026-09-24"},
            {"supervisor": self.supervisor.id, "instalacion": "Norte", "persona": "Soto", "fecha_desde": "2026-09-24", "fecha_hasta": "2026-09-24"},
        ]:
            with self.subTest(filters=filters):
                response = self.client.get(self.endpoint, filters)
                self.assertEqual(response.status_code, 200)
                self.assertEqual([item["id"] for item in response.data["results"]], [first.id])
        self.assertEqual(self.client.get(self.endpoint, {"instalacion": "Norte", "persona": "María"}).data["count"], 0)

    def test_invalid_filters_return_validation_error(self):
        for filters in [{"supervisor": "invalid"}, {"fecha_desde": "invalid"}, {"fecha_desde": "2026-09-25", "fecha_hasta": "2026-09-24"}]:
            self.assertEqual(self.client.get(self.endpoint, filters).status_code, 400)

    def test_filter_options_are_scoped(self):
        self.expense()
        self.expense(self.other)
        response = self.client.get(f"{self.endpoint}filtros/")
        self.assertEqual(len(response.data["supervisores"]), 1)
        self.client.force_authenticate(self.admin)
        self.assertEqual(len(self.client.get(f"{self.endpoint}filtros/").data["supervisores"]), 2)

    def test_authentication_required_and_records_cannot_be_modified(self):
        expense = self.expense()
        self.assertEqual(self.client.patch(f"{self.endpoint}{expense.id}/", {"persona": "Alterado"}).status_code, 405)
        self.assertEqual(self.client.delete(f"{self.endpoint}{expense.id}/").status_code, 405)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.endpoint).status_code, 401)
        self.assertEqual(self.client.post(self.endpoint, {}, format="multipart").status_code, 401)

    def test_pagination(self):
        for _ in range(21):
            self.expense()
        response = self.client.get(self.endpoint)
        self.assertEqual(response.data["count"], 21)
        self.assertEqual(len(response.data["results"]), 20)
        self.assertEqual(len(self.client.get(self.endpoint, {"page": 2}).data["results"]), 1)
