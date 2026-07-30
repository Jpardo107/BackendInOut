from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from instalacion.models import Instalacion
from user.models import Cargo
from .models import (
    PostulacionGuardia,
    PreferenciaVacantePostulante,
    PreguntaPostulacion,
    TipoInstalacionLaboral,
    TokenQrPostulacion,
    VacanteGuardia,
)
from .serializers import validar_rut_chileno
from .views import token_hash


class PostulacionesApiTests(APITestCase):
    def setUp(self):
        self.general = TipoInstalacionLaboral.objects.get(slug="general")
        self.bodega = TipoInstalacionLaboral.objects.get(slug="bodega")
        self.condominio = TipoInstalacionLaboral.objects.get(slug="condominio")
        self.instalacion = Instalacion.objects.create(
            nombre="CLIENTE SECRETO", direccion="DIRECCION SECRETA 123",
            comuna="Renca", nombre_contacto="Contacto secreto",
            correo_contacto="secreto@example.com", telefono_contacto="999999999",
        )
        self.vacante = VacanteGuardia.objects.create(
            instalacion=self.instalacion, tipo_instalacion=self.bodega,
            comuna_publica="Renca", descripcion_publica="Guardia 4x4 noche",
            jornada="Completa", sistema_turno="4x4", sueldo=650000,
            estado="publicado", cantidad_cupos=2,
        )
        self.raw_token = "token-seguro-de-prueba"
        self.postulacion = PostulacionGuardia.objects.create(
            nombres="Ana", apellido_paterno="Pérez", rut="189356870",
            telefono="+56912345678", email="ana@example.com",
            comuna_residencia="Maipú", acceso_hash=token_hash(self.raw_token),
            presentacion="Tengo experiencia en seguridad y buenas habilidades de comunicación.",
        )
        self.headers = {"HTTP_X_POSTULACION_TOKEN": self.raw_token}

    def test_valida_rut_chileno(self):
        self.assertEqual(validar_rut_chileno("18.935.687-0"), "189356870")
        with self.assertRaises(Exception):
            validar_rut_chileno("18.935.687-1")

    def test_vacante_publica_no_expone_instalacion(self):
        response = self.client.get("/api/postulaciones/publicas/postulaciones/vacantes/")
        self.assertEqual(response.status_code, 200)
        payload = response.data[0]
        self.assertNotIn("instalacion", payload)
        self.assertNotIn("direccion", payload)
        self.assertNotIn("nombre", payload)
        self.assertNotIn("CLIENTE SECRETO", str(payload))

    def test_token_no_permite_acceder_a_otra_postulacion(self):
        otra = PostulacionGuardia.objects.create(
            nombres="Beto", apellido_paterno="Soto", rut="8801779K",
            telefono="+56987654321", email="beto@example.com",
            comuna_residencia="Renca", acceso_hash=token_hash("otro-token"),
        )
        response = self.client.get(
            f"/api/postulaciones/publicas/postulaciones/{otra.id_publico}/",
            **self.headers,
        )
        self.assertEqual(response.status_code, 403)

    def test_evaluacion_mezcla_general_y_tipos_sin_duplicados(self):
        vacante_condominio = VacanteGuardia.objects.create(
            instalacion=self.instalacion, tipo_instalacion=self.condominio,
            comuna_publica="Santiago", descripcion_publica="Guardia condominio",
            jornada="Completa", sistema_turno="4x4", sueldo=620000,
            estado="publicado", cantidad_cupos=1,
        )
        PreferenciaVacantePostulante.objects.create(postulacion=self.postulacion, vacante=self.vacante, orden_preferencia=1)
        PreferenciaVacantePostulante.objects.create(postulacion=self.postulacion, vacante=vacante_condominio, orden_preferencia=2)
        for tipo in (self.general, self.bodega, self.condominio):
            for index in range(3):
                PreguntaPostulacion.objects.create(
                    texto=f"{tipo.nombre} {index}", tipo_instalacion=tipo,
                    tipo_respuesta="texto_largo", orden=index,
                )
        response = self.client.post(
            f"/api/postulaciones/publicas/postulaciones/{self.postulacion.id_publico}/evaluacion/",
            {}, format="json", **self.headers,
        )
        self.assertEqual(response.status_code, 200)
        textos = [item["texto"] for item in response.data["preguntas"]]
        self.assertEqual(len(textos), 9)
        self.assertEqual(len(textos), len(set(textos)))

    def test_qr_requiere_usuario_autorizado_y_rechaza_revocado(self):
        qr = TokenQrPostulacion.objects.create(postulacion=self.postulacion)
        unauthenticated = self.client.get(f"/api/postulaciones/admin/postulaciones/verificar-qr/{qr.token}/")
        self.assertEqual(unauthenticated.status_code, 401)
        cargo = Cargo.objects.create(nombre="Encargado RRHH")
        user = get_user_model().objects.create_user(
            username="rrhh.postulaciones", password="test-pass", nombres="RRHH",
            apellidos="Test", rut="11111111-1", email="rrhh.post@example.com", cargo=cargo,
        )
        self.client.force_authenticate(user=user)
        qr.activo = False
        qr.save()
        response = self.client.get(f"/api/postulaciones/admin/postulaciones/verificar-qr/{qr.token}/")
        self.assertEqual(response.status_code, 404)

    @patch("postulaciones.views.upload_document")
    def test_documento_valida_contenido_y_guarda_key_privada(self, upload_mock):
        pdf = b"%PDF-1.4 archivo de prueba"
        from django.core.files.uploadedfile import SimpleUploadedFile
        archivo = SimpleUploadedFile("cv.pdf", pdf, content_type="application/pdf")
        response = self.client.post(
            f"/api/postulaciones/publicas/postulaciones/{self.postulacion.id_publico}/documentos/",
            {"tipo_documento": "curriculum", "archivo": archivo},
            format="multipart", **self.headers,
        )
        self.assertEqual(response.status_code, 201)
        self.assertNotIn(self.postulacion.rut, upload_mock.call_args.args[1])
