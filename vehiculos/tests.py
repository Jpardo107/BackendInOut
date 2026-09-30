import json
from io import BytesIO
from unittest.mock import patch
from uuid import uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image
from rest_framework.test import APIClient

from user.models import Cargo, Usuario
from .models import FotoVehiculo, MovimientoVehiculo, Vehiculo


class VehicleTests(TestCase):
    endpoint = "/api/vehiculos/"

    def setUp(self):
        cargo = Cargo.objects.create(nombre="Supervisor")
        self.supervisor = self.user("ana", cargo=cargo)
        self.other = self.user("luis", cargo=cargo)
        self.admin = self.user("admin", cargo=Cargo.objects.create(nombre="Administrador"))
        self.outsider = self.user("guardia", cargo=Cargo.objects.create(nombre="Guardia"))
        self.vehicle = Vehiculo.objects.create(patente="ABCD12", marca="Toyota", modelo="Yaris",
                                               kilometraje_actual=100, kilometraje_mantencion=200)
        self.client = APIClient()
        self.client.force_authenticate(self.supervisor)
        self.upload = self.enterContext(patch("vehiculos.views.upload_document"))
        self.delete = self.enterContext(patch("vehiculos.views.delete_document"))

    def user(self, name, **kwargs):
        return Usuario.objects.create_user(username=name, nombres=name, apellidos="Prueba",
                                           rut=name, email=f"{name}@example.test", **kwargs)

    def payload(self, **changes):
        self.vehicle.refresh_from_db()
        result = {
            "solicitud_id": str(uuid4()), "version": self.vehicle.version,
            "tipo": "recepcion", "kilometraje": 110,
            "gata": True, "llave_cruz": True, "extintor": False, "triangulo": True, "resumen": "",
            "fotos": [{"vista": vista, "tiene_novedad": False, "novedad": ""}
                      for vista in ("frontal", "trasera", "izquierdo", "derecho", "tablero")],
        }
        result.update(changes)
        return result

    def image(self):
        buffer = BytesIO()
        Image.new("RGB", (10, 10), "white").save(buffer, format="PNG")
        return SimpleUploadedFile("foto.png", buffer.getvalue(), content_type="image/png")

    def post(self, data=None, missing=None, user=None):
        if user:
            self.client.force_authenticate(user)
        data = data or self.payload()
        files = {f"foto_{index}": self.image() for index in range(len(data.get("fotos", []))) if index != missing}
        return self.client.post(f"{self.endpoint}{self.vehicle.pk}/movimiento/",
                                {"datos": json.dumps(data), **files}, format="multipart")

    def test_complete_handoff_and_defaults(self):
        response = self.post()
        self.assertEqual(response.status_code, 201, response.data)
        reception_id = response.data["id"]
        self.assertEqual(response.data["resumen"], "Recepción sin observaciones")
        self.assertEqual(len(response.data["fotos"]), 5)
        self.assertFalse(response.data["extintor"])
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.supervisor_actual, self.supervisor)
        self.assertEqual(self.vehicle.kilometraje_actual, 110)
        self.assertEqual(self.post(self.payload(kilometraje=120), user=self.other).status_code, 409)
        self.assertEqual(self.post(self.payload(tipo="entrega", kilometraje=120)).status_code, 409)
        response = self.post(self.payload(tipo="entrega", kilometraje=200, resumen="  "), user=self.supervisor)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["resumen"], "Entrega sin observaciones")
        self.assertEqual(response.data["recepcion"], reception_id)
        self.vehicle.refresh_from_db()
        self.assertIsNone(self.vehicle.supervisor_actual)
        detail = self.client.get(f"{self.endpoint}{self.vehicle.pk}/").data
        self.assertTrue(detail["requiere_mantencion"])
        self.assertEqual(self.post(self.payload(kilometraje=201), user=self.other).status_code, 201)

    def test_repeated_request_does_not_duplicate_or_take_back_vehicle(self):
        payload = self.payload()
        first = self.post(payload)
        second = self.post(payload)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(self.upload.call_count, 5)
        self.post(self.payload(tipo="entrega", kilometraje=120))
        self.post(self.payload(kilometraje=125), user=self.other)
        third = self.post(payload, user=self.supervisor)
        self.assertEqual(third.status_code, 200)
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.supervisor_actual, self.other)
        self.assertEqual(MovimientoVehiculo.objects.count(), 3)

    def test_reused_request_id_cannot_impersonate_another_supervisor(self):
        payload = self.payload()
        self.post(payload)
        self.assertEqual(self.post(payload, user=self.other).status_code, 409)

    def test_missing_images_invalid_image_and_mandatory_views(self):
        self.assertEqual(self.post(missing=4).status_code, 400)
        data = self.payload()
        data["fotos"][4]["vista"] = "frontal"
        self.assertEqual(self.post(data).status_code, 400)
        data = self.payload()
        files = {f"foto_{i}": self.image() for i in range(5)}
        files["foto_2"] = SimpleUploadedFile("fake.jpg", b"not an image", content_type="image/jpeg")
        response = self.client.post(f"{self.endpoint}{self.vehicle.pk}/movimiento/",
                                    {"datos": json.dumps(data), **files}, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.upload.assert_not_called()
        self.assertFalse(MovimientoVehiculo.objects.exists())

    def test_extra_photos_and_novedades(self):
        data = self.payload()
        data["fotos"][0].update(tiene_novedad=True, novedad="   ")
        self.assertEqual(self.post(data).status_code, 400)
        data["fotos"][0]["novedad"] = "Parachoques rayado"
        data["fotos"][1]["novedad"] = "Debe descartarse con switch apagado"
        data["fotos"].append({"vista": "extra", "tiene_novedad": True, "novedad": "Abolladura puerta"})
        response = self.post(data)
        self.assertEqual(response.status_code, 201, response.data)
        photos = response.data["fotos"]
        self.assertEqual(len(photos), 6)
        self.assertEqual(photos[0]["novedad"], "Parachoques rayado")
        self.assertEqual(photos[1]["novedad"], "")
        self.assertEqual(photos[5]["novedad"], "Abolladura puerta")

    def test_checklist_and_kilometers_are_validated(self):
        for value in (-1, 99, 1.5, "abc", None):
            with self.subTest(value=value):
                self.assertEqual(self.post(self.payload(kilometraje=value)).status_code, 400)
        for key in ("gata", "llave_cruz", "extintor", "triangulo"):
            data = self.payload()
            del data[key]
            self.assertEqual(self.post(data).status_code, 400)
        self.upload.assert_not_called()
        self.assertEqual(self.post().status_code, 201)
        self.assertEqual(self.post(self.payload(tipo="entrega", kilometraje=105)).status_code, 400)

    def test_failed_delivery_upload_preserves_custody_and_cleans_files(self):
        self.post()
        self.upload.reset_mock()
        self.upload.side_effect = [None, RuntimeError("storage unavailable")]
        with self.assertLogs("vehiculos.views", level="ERROR"):
            response = self.post(self.payload(tipo="entrega", kilometraje=130))
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.delete.call_count, 2)
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.supervisor_actual, self.supervisor)
        self.assertEqual(self.vehicle.kilometraje_actual, 110)
        self.assertEqual(MovimientoVehiculo.objects.count(), 1)
        self.assertEqual(FotoVehiculo.objects.count(), 5)

    def test_database_failure_rolls_back_custody_and_removes_uploaded_photos(self):
        from django.db import IntegrityError
        with patch("vehiculos.views.FotoVehiculo.objects.bulk_create", side_effect=IntegrityError("failure")):
            response = self.post()
        self.assertEqual(response.status_code, 409)
        self.vehicle.refresh_from_db()
        self.assertIsNone(self.vehicle.supervisor_actual)
        self.assertEqual(self.vehicle.kilometraje_actual, 100)
        self.assertEqual(self.delete.call_count, 5)
        self.assertFalse(MovimientoVehiculo.objects.exists())

    def test_another_reception_committing_during_upload_wins_exclusively(self):
        concurrent_client = APIClient()
        concurrent_client.force_authenticate(self.other)
        payload = self.payload()
        started = False

        def receive_while_uploading(*args):
            nonlocal started
            if started:
                return
            started = True
            response = concurrent_client.post(f"{self.endpoint}{self.vehicle.pk}/movimiento/",
                {"datos": json.dumps(self.payload()), **{f"foto_{i}": self.image() for i in range(5)}}, format="multipart")
            self.assertEqual(response.status_code, 201, response.data)

        self.upload.side_effect = receive_while_uploading
        response = self.post(payload)
        self.assertEqual(response.status_code, 409)
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.supervisor_actual, self.other)
        self.assertEqual(MovimientoVehiculo.objects.count(), 1)
        self.assertEqual(FotoVehiculo.objects.count(), 5)
        self.assertEqual(self.delete.call_count, 5)

    def test_stale_delivery_cannot_close_a_new_reception(self):
        self.post()
        old_delivery = self.payload(tipo="entrega", kilometraje=150)
        self.post(self.payload(tipo="entrega", kilometraje=120))
        self.post(self.payload(kilometraje=130))
        self.assertEqual(self.post(old_delivery).status_code, 409)
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.supervisor_actual, self.supervisor)

    def test_permissions_and_private_photo_access(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.endpoint).status_code, 401)
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(self.endpoint).status_code, 403)
        self.client.force_authenticate(self.supervisor)
        self.assertEqual(self.client.post(self.endpoint, {}, format="json").status_code, 403)
        self.assertEqual(self.client.patch(f"{self.endpoint}{self.vehicle.pk}/", {"activo": False}).status_code, 403)
        self.assertEqual(self.client.delete(f"{self.endpoint}{self.vehicle.pk}/").status_code, 403)
        result = self.post()
        photo_id = result.data["fotos"][0]["id"]
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(f"{self.endpoint}{self.vehicle.pk}/historial/").data["count"], 0)
        self.assertEqual(self.client.get(f"{self.endpoint}{self.vehicle.pk}/foto/?foto={photo_id}").status_code, 404)
        self.client.force_authenticate(self.admin)
        history = self.client.get(f"{self.endpoint}{self.vehicle.pk}/historial/")
        self.assertEqual(history.data["count"], 1)
        self.assertNotIn("storage_key", history.data["results"][0]["fotos"][0])
        with patch("vehiculos.views.generate_signed_url", return_value="https://example.test/private"):
            self.assertEqual(self.client.get(f"{self.endpoint}{self.vehicle.pk}/foto/?foto={photo_id}").status_code, 200)
        self.assertEqual(self.post(self.payload(tipo="entrega", kilometraje=120)).status_code, 403)

    def test_admin_crud_normalization_and_protected_history(self):
        self.client.force_authenticate(self.admin)
        result = self.client.post(self.endpoint, {"patente": " xy-zt 34 ", "marca": "Kia", "modelo": "Rio", "kilometraje_actual": 0, "kilometraje_mantencion": 1000}, format="json")
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(result.data["patente"], "XYZT34")
        duplicate = self.client.post(self.endpoint, {"patente": "xyzt-34", "marca": "Kia", "modelo": "Rio"}, format="json")
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(self.client.delete(f"{self.endpoint}{result.data['id']}/").status_code, 204)
        response = self.client.patch(f"{self.endpoint}{self.vehicle.pk}/", {"kilometraje_mantencion": 300}, format="json")
        self.assertEqual(response.status_code, 200)
        self.post(user=self.supervisor)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.delete(f"{self.endpoint}{self.vehicle.pk}/").status_code, 409)
        self.assertEqual(self.client.patch(f"{self.endpoint}{self.vehicle.pk}/", {"activo": False}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(f"{self.endpoint}{self.vehicle.pk}/", {"kilometraje_actual": 500}, format="json").status_code, 400)
        self.post(self.payload(tipo="entrega", kilometraje=120), user=self.supervisor)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.delete(f"{self.endpoint}{self.vehicle.pk}/").status_code, 400)
        self.assertEqual(self.client.patch(f"{self.endpoint}{self.vehicle.pk}/", {"activo": False}, format="json").status_code, 200)
        self.assertEqual(self.client.get(f"{self.endpoint}{self.vehicle.pk}/historial/").data["count"], 2)
        self.client.force_authenticate(self.supervisor)
        self.assertEqual(self.client.get(self.endpoint).data["results"], [])
        self.assertEqual(self.post(self.payload(kilometraje=130)).status_code, 404)
