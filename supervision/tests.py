from datetime import date, time
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from instalacion.models import Instalacion
from user.models import Cargo, Usuario
from .views import SupervisionViewSet
from .models import SupervisionActiva


class SupervisionLiveEventTests(SimpleTestCase):
    @patch("supervision.views.SupervisionActiva.objects.filter")
    @patch("supervision.views.schedule_live_event")
    def test_crear_supervision_programa_eventos_resumidos(self, publish_mock, active_filter_mock):
        supervision = SimpleNamespace(
            id=91,
            instalacion_id=12,
            instalacion=SimpleNamespace(nombre="PLANTA EVENTOS"),
            supervisor_id=7,
            supervisor=SimpleNamespace(nombres="Sara", apellidos="Soto"),
            fecha=date(2026, 8, 8),
            hora_inicio=time(10, 0),
            hora_final=time(10, 30),
            novedades="Sin novedades",
            solicitudes="Reponer extintor",
            estado_solicitud="pendiente",
        )
        serializer = Mock()
        serializer.save.return_value = supervision

        SupervisionViewSet().perform_create(serializer)
        active_filter_mock.return_value.delete.assert_called_once()

        event_types = [call.args[0] for call in publish_mock.call_args_list]
        self.assertEqual(event_types, [
            "supervision.created", "supervision.completed", "solicitud.created"
        ])
        self.assertEqual(publish_mock.call_args_list[0].args[1]["id"], 91)
        completed = publish_mock.call_args_list[1].args[1]
        self.assertEqual(completed["novedades"], "Sin novedades")
        self.assertEqual(completed["solicitudes"], "Reponer extintor")


class SupervisionStartTests(TestCase):
    def setUp(self):
        cargo = Cargo.objects.create(nombre="Supervisor")
        self.supervisor = Usuario.objects.create_user(
            username="supervisor.qr",
            password="test-pass",
            nombres="Ana",
            apellidos="Pérez",
            rut="17777777-7",
            email="supervisor.qr@example.com",
            cargo=cargo,
        )
        self.instalacion = Instalacion.objects.create(
            nombre="Planta Norte",
            direccion="Ruta 5",
            comuna="Lampa",
            nombre_contacto="Contacto",
            correo_contacto="contacto@example.com",
            telefono_contacto="+56911111111",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.supervisor)

    @patch("supervision.views.schedule_live_event")
    def test_escaneo_registra_evento_de_inicio_con_usuario_autenticado(self, publish_mock):
        response = self.client.post(
            "/api/supervision/supervisiones/iniciar/",
            {
                "instalacion": self.instalacion.id,
                "latitud": -33.4489,
                "longitud": -70.6693,
                "fecha": "2026-08-08",
                "hora_inicio": "15:42:10",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["instalacion"], "Planta Norte")
        self.assertEqual(response.data["supervisor"], "Ana Pérez")
        self.assertEqual(response.data["latitud"], -33.4489)
        self.assertEqual(response.data["fecha"], "2026-08-08")
        self.assertEqual(response.data["hora_inicio"], "15:42:10")
        active = self.supervisor.supervision_activa
        self.assertEqual(active.instalacion, self.instalacion)
        self.assertEqual(active.hora_inicio, time(15, 42, 10))
        publish_mock.assert_called_once()
        self.assertEqual(publish_mock.call_args.args[0], "supervision.started")

    def test_inicio_rechaza_instalacion_inexistente(self):
        response = self.client.post(
            "/api/supervision/supervisiones/iniciar/",
            {"instalacion": 999999},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_recupera_supervision_activa_del_usuario(self):
        self.client.post(
            "/api/supervision/supervisiones/iniciar/",
            {
                "instalacion": self.instalacion.id,
                "latitud": -33.4489,
                "longitud": -70.6693,
                "fecha": "2026-08-08",
                "hora_inicio": "15:42:10",
            },
            format="json",
        )
        response = self.client.get("/api/supervision/supervisiones/activa/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["instalacion_detalle"]["nombre"], "Planta Norte")
        self.assertEqual(response.data["hora_inicio"], "15:42:10")

        delete_response = self.client.delete("/api/supervision/supervisiones/activa/")
        self.assertEqual(delete_response.status_code, 204)
        self.assertFalse(SupervisionActiva.objects.filter(supervisor=self.supervisor).exists())


class FotoSupervisionUploadTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from rest_framework.test import APIClient

        self.user = get_user_model().objects.create_user(username="sup-fotos", password="x")
        self.client = APIClient()

    def test_requiere_autenticacion(self):
        response = self.client.post("/api/supervision/fotos/upload/", {}, format="multipart")
        self.assertIn(response.status_code, (401, 403))

    def test_sube_y_sirve_foto(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.test import override_settings

        self.client.force_authenticate(self.user)
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=Path(media_root)), patch("supervision.storage._r2_enabled", return_value=False):
            foto = SimpleUploadedFile("foto.jpg", b"\xff\xd8\xff\xe0contenido", content_type="image/jpeg")
            response = self.client.post("/api/supervision/fotos/upload/", {"files[]": [foto]}, format="multipart")
            self.assertEqual(response.status_code, 201, response.content)
            item = response.json()["files"][0]
            self.assertTrue(item["url"].endswith(item["key"]))
            self.assertTrue(item["key"].startswith("supervision/fotos/"))

            self.client.force_authenticate(None)
            public = self.client.get(f"/api/supervision/fotos/media/{item['key']}")
            self.assertEqual(public.status_code, 200)
            self.assertEqual(b"".join(public.streaming_content), b"\xff\xd8\xff\xe0contenido")
            self.assertEqual(self.client.get("/api/supervision/fotos/media/vivadent/images/x.jpg").status_code, 404)

    def test_rechaza_extension_no_permitida(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.force_authenticate(self.user)
        archivo = SimpleUploadedFile("script.php", b"<?php", content_type="application/x-php")
        response = self.client.post("/api/supervision/fotos/upload/", {"files[]": [archivo]}, format="multipart")
        self.assertEqual(response.status_code, 400)


class MigrarFotosCpanelTests(TestCase):
    def test_copia_en_ruta_predecible_sin_tocar_la_bd(self):
        from io import StringIO
        from unittest.mock import MagicMock, patch
        from django.core.management import call_command
        from instalacion.models import Instalacion
        from supervision.models import FotoSupervision, Supervision

        foto = FotoSupervision.objects.create(
            supervision=Supervision.objects.create(instalacion=Instalacion.objects.create(nombre="X"), fecha=date(2026, 11, 1), hora_inicio=time(9), hora_final=time(10)),
            url_imagen="https://inout.jaimepardo.cl/uploads/foto%201.jpg",
        )
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b"img"
        response.headers.get_content_type.return_value = "image/jpeg"
        with patch("supervision.management.commands.migrar_fotos_supervision.urlopen", return_value=response), patch(
            "supervision.management.commands.migrar_fotos_supervision.save_supervision_photo"
        ) as save:
            call_command("migrar_fotos_supervision", stdout=StringIO())
        self.assertEqual(save.call_args.kwargs["key"], "supervision/fotos/cpanel/uploads/foto 1.jpg")
        foto.refresh_from_db()
        self.assertEqual(foto.url_imagen, "https://inout.jaimepardo.cl/uploads/foto%201.jpg")


class ResumenSolicitudesTests(TestCase):
    def setUp(self):
        from datetime import datetime
        from django.contrib.auth import get_user_model
        from instalacion.models import Instalacion
        from supervision.models import ConfiguracionResumenSolicitudes
        from supervision.resumen_solicitudes import CHILE_TZ

        self.tz = CHILE_TZ
        self.supervisor = get_user_model().objects.create_user(username="sup-resumen", password="x", nombres="Ana", apellidos="Rojas")
        self.instalacion = Instalacion.objects.create(nombre="Mall Centro")
        ConfiguracionResumenSolicitudes.objects.create(pk=1, destinatarios=["a@inout.cl", "b@inout.cl", "c@inout.cl"])
        # Martes 24-11-2026 07:00 hora Chile.
        self.ahora = datetime(2026, 11, 24, 7, 0, tzinfo=CHILE_TZ)

    def crear(self, solicitudes, creada_en):
        from supervision.models import Supervision

        supervision = Supervision.objects.create(
            instalacion=self.instalacion, supervisor=self.supervisor, fecha=creada_en.date(),
            hora_inicio=time(8), hora_final=time(9), solicitudes=solicitudes,
        )
        Supervision.objects.filter(pk=supervision.pk).update(creada_en=creada_en)
        return supervision

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", INFORMACIONES_FROM_EMAIL="informaciones@inout.cl")
    def test_envia_solicitudes_de_las_ultimas_24_horas(self):
        from datetime import timedelta
        from django.core import mail
        from supervision.resumen_solicitudes import enviar_resumen

        self.crear("Faltan 2 linternas", self.ahora - timedelta(hours=3))
        self.crear("Sin solicitudes", self.ahora - timedelta(hours=2))
        self.crear("Antigua", self.ahora - timedelta(hours=25))
        envio = enviar_resumen(self.ahora)

        self.assertTrue(envio.enviado)
        self.assertEqual(envio.cantidad, 1)
        self.assertEqual(len(mail.outbox), 1)
        correo = mail.outbox[0]
        self.assertEqual(correo.from_email, "informaciones@inout.cl")
        self.assertEqual(correo.to, ["a@inout.cl", "b@inout.cl", "c@inout.cl"])
        self.assertIn("Ana Rojas", correo.body)
        self.assertIn("Mall Centro", correo.body)
        self.assertIn("Faltan 2 linternas", correo.body)
        self.assertIn("24-11-2026 04:00", correo.body)
        self.assertNotIn("Antigua", correo.body)

    def test_lunes_incluye_fin_de_semana(self):
        from datetime import datetime, timedelta
        from supervision.resumen_solicitudes import solicitudes_entre, ventana_envio

        lunes = datetime(2026, 11, 23, 7, 0, tzinfo=self.tz)
        self.crear("Del sábado", lunes - timedelta(hours=40))
        self.assertEqual([f["detalle"] for f in solicitudes_entre(*ventana_envio(lunes))], ["Del sábado"])

    def test_supervision_antigua_sin_creada_en_usa_fecha_y_hora_final(self):
        from datetime import datetime, timedelta
        from supervision.models import Supervision
        from supervision.resumen_solicitudes import solicitudes_entre

        supervision = self.crear("Legacy", self.ahora)
        Supervision.objects.filter(pk=supervision.pk).update(creada_en=None, fecha=date(2026, 11, 23), hora_final=time(18, 30))
        filas = solicitudes_entre(self.ahora - timedelta(hours=24), self.ahora)
        self.assertEqual(filas[0]["momento"], datetime(2026, 11, 23, 18, 30, tzinfo=self.tz))

    def test_programacion_solo_lunes_a_viernes_a_las_7_y_una_vez(self):
        from datetime import datetime
        from supervision.models import EnvioResumenSolicitudes
        from supervision.resumen_solicitudes import debe_enviar_programado

        self.assertTrue(debe_enviar_programado(self.ahora)[0])
        self.assertFalse(debe_enviar_programado(self.ahora.replace(hour=8))[0])
        self.assertFalse(debe_enviar_programado(datetime(2026, 11, 28, 7, 0, tzinfo=self.tz))[0])
        EnvioResumenSolicitudes.objects.create(fecha=self.ahora.date(), desde=self.ahora, hasta=self.ahora, enviado=True)
        self.assertFalse(debe_enviar_programado(self.ahora)[0])

    def test_configuracion_valida_correos_y_permisos(self):
        from django.contrib.auth import get_user_model
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(self.supervisor)
        self.assertEqual(client.get("/api/supervision/correo-solicitudes/").status_code, 403)

        admin = get_user_model().objects.create_user(username="admin-resumen", password="x", email="adm@inout.cl", rut="11111111-1", is_staff=True)
        client.force_authenticate(admin)
        response = client.put("/api/supervision/correo-solicitudes/", {"destinatarios": ["X@inout.cl", "x@inout.cl", "y@inout.cl"]}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["destinatarios"], ["x@inout.cl", "y@inout.cl"])
        self.assertEqual(client.put("/api/supervision/correo-solicitudes/", {"destinatarios": ["no-es-correo"]}, format="json").status_code, 400)
