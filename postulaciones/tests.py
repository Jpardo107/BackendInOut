from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from instalacion.models import Instalacion
from user.models import Cargo
from .models import (
    ClaveTemporalPostulacion,
    DocumentoPostulacion,
    PostulacionGuardia,
    EvaluacionPostulacion,
    PreferenciaVacantePostulante,
    PreguntaPostulacion,
    PreguntaAsignadaEvaluacion,
    RespuestaPostulacion,
    TipoInstalacionLaboral,
    TokenQrPostulacion,
    VacanteGuardia,
)
from .serializers import formatear_rut_chileno, validar_rut_chileno
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
            fecha_nacimiento="1990-05-20", disponible_4x4=True, disponible_dia=True,
            sin_estudios=True, sin_experiencia=True,
        )
        self.headers = {"HTTP_X_POSTULACION_TOKEN": self.raw_token}

    def test_valida_rut_chileno(self):
        self.assertEqual(validar_rut_chileno("18.935.687-0"), "189356870")
        self.assertEqual(formatear_rut_chileno("189356870"), "18.935.687-0")
        with self.assertRaises(Exception):
            validar_rut_chileno("18.935.687-1")

    def test_permite_continuar_sin_vacantes_para_banco(self):
        response = self.client.put(
            f"/api/postulaciones/publicas/postulaciones/{self.postulacion.id_publico}/preferencias/",
            {"vacantes": []}, format="json", **self.headers,
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["preferencias"], [])

        evaluacion = EvaluacionPostulacion.objects.create(postulacion=self.postulacion)
        asignada = PreguntaAsignadaEvaluacion.objects.create(
            evaluacion=evaluacion, texto="Pregunta obligatoria", tipo_respuesta="texto_corto",
            obligatoria=True, tipo_instalacion_nombre="General",
        )
        RespuestaPostulacion.objects.create(pregunta_asignada=asignada, respuesta="Respuesta")
        DocumentoPostulacion.objects.create(
            postulacion=self.postulacion, tipo_documento="curriculum", nombre_original="cv-ana.pdf",
            storage_key="postulaciones/prueba/cv.pdf", mime_type="application/pdf", size=100,
        )
        final = self.client.post(
            f"/api/postulaciones/publicas/postulaciones/{self.postulacion.id_publico}/finalizar/",
            {"declaracion_veracidad": True, "consentimiento_datos": True},
            format="json", **self.headers,
        )
        self.assertEqual(final.status_code, 200, final.data)
        self.postulacion.refresh_from_db()
        self.assertEqual(self.postulacion.estado, "banco_postulantes")

    @patch("postulaciones.views.send_mail")
    def test_clave_temporal_crea_nueva_postulacion_con_datos_y_documentos(self, send_mail_mock):
        self.postulacion.estado = "finalizada"
        self.postulacion.save(update_fields=("estado",))
        documento = DocumentoPostulacion.objects.create(
            postulacion=self.postulacion, tipo_documento="curriculum", nombre_original="Curriculum Ana.pdf",
            storage_key="postulaciones/ana/cv.pdf", mime_type="application/pdf", size=123,
        )
        solicitud = self.client.post(
            "/api/postulaciones/publicas/postulaciones/solicitar-clave/",
            {"rut": "18.935.687-0"}, format="json",
        )
        self.assertEqual(solicitud.status_code, 200, solicitud.data)
        send_mail_mock.assert_called_once()
        clave = ClaveTemporalPostulacion.objects.get(rut="189356870")
        clave.codigo_hash = token_hash("123456")
        clave.save(update_fields=("codigo_hash",))

        verificacion = self.client.post(
            "/api/postulaciones/publicas/postulaciones/verificar-clave/",
            {"rut": "18.935.687-0", "codigo": "123456"}, format="json",
        )
        self.assertEqual(verificacion.status_code, 200, verificacion.data)
        self.assertEqual(verificacion.data["resume_at"], "vacantes")
        nueva = PostulacionGuardia.objects.get(id_publico=verificacion.data["postulacion"]["id_publico"])
        self.assertNotEqual(nueva.pk, self.postulacion.pk)
        copia = nueva.documentos.get()
        self.assertEqual(copia.nombre_original, "Curriculum Ana.pdf")
        self.assertEqual(copia.storage_key, documento.storage_key)

    def test_cors_permite_origen_y_header_token_postulacion(self):
        response = self.client.options(
            f"/api/postulaciones/publicas/postulaciones/{self.postulacion.id_publico}/",
            HTTP_ORIGIN="https://postulaciones.ejemplo.cl",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="x-postulacion-token,content-type",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Access-Control-Allow-Origin"], "*")
        allowed_headers = response["Access-Control-Allow-Headers"].lower()
        self.assertIn("x-postulacion-token", allowed_headers)
        self.assertIn("content-type", allowed_headers)

    def test_vacante_publica_no_expone_instalacion(self):
        response = self.client.get("/api/postulaciones/publicas/postulaciones/vacantes/")
        self.assertEqual(response.status_code, 200)
        payload = response.data[0]
        self.assertNotIn("instalacion", payload)
        self.assertNotIn("direccion", payload)
        self.assertNotIn("nombre", payload)
        self.assertNotIn("CLIENTE SECRETO", str(payload))

    def test_listado_publico_solo_muestra_vacantes_publicadas(self):
        vacante_terminada = VacanteGuardia.objects.create(
            instalacion=self.instalacion, tipo_instalacion=self.bodega,
            comuna_publica="Renca", descripcion_publica="Vacante terminada",
            jornada="Completa", sistema_turno="4x4", sueldo=650000,
            estado="cerrado", cantidad_cupos=2,
        )

        response = self.client.get("/api/postulaciones/publicas/postulaciones/vacantes/")

        self.assertEqual(response.status_code, 200)
        ids = {item["public_id"] for item in response.data}
        self.assertIn(str(self.vacante.public_id), ids)
        self.assertNotIn(str(vacante_terminada.public_id), ids)
        self.assertTrue(all(item["estado"] == "publicado" for item in response.data))

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

    @patch("postulaciones.views.analizar_perfil_con_ia")
    def test_admin_puede_analizar_perfil_por_post(self, analizar_mock):
        analizar_mock.return_value = {
            "score_curriculum": 15,
            "score_evaluacion": 16,
            "resumen": "Perfil compatible sujeto a revisión humana.",
            "fortalezas": ["Experiencia"],
            "aspectos_a_validar": ["Referencias"],
        }
        cargo = Cargo.objects.create(nombre="Encargado RRHH")
        user = get_user_model().objects.create_user(
            username="rrhh.analisis", password="test-pass", nombres="RRHH",
            apellidos="Análisis", rut="11111111-1", email="analisis@example.com", cargo=cargo,
        )
        self.client.force_authenticate(user=user)
        response = self.client.post(
            f"/api/postulaciones/admin/postulaciones/{self.postulacion.id}/analizar-perfil/",
            {}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["score_perfil"]["total"], 56)
        analizar_mock.assert_called_once()

    def test_guarda_primer_paso_completo(self):
        payload = {
            "nombres": "Ana María",
            "apellido_paterno": "Pérez",
            "apellido_materno": "Soto",
            "fecha_nacimiento": "1990-05-20",
            "nacionalidad": "Chilena",
            "telefono": "+56 9 1234 5678",
            "email": "ana@example.com",
            "comuna_residencia": "Maipú",
            "direccion": "Calle Uno 123",
            "situacion_migratoria": "",
            "disponibilidad_incorporacion": "2026-08-15",
            "tiene_licencia": True,
            "clase_licencia": "B",
            "movilizacion_propia": False,
            "disponible_dia": True,
            "disponible_noche": True,
            "disponible_4x4": True,
            "disponible_5x2": False,
            "estado_os10": "vigente",
            "os10_vencimiento": "2027-01-31",
            "os10_numero": "OS10-123",
            "paso_actual": 2,
        }
        response = self.client.patch(
            f"/api/postulaciones/publicas/postulaciones/{self.postulacion.id_publico}/",
            payload,
            format="json",
            **self.headers,
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.postulacion.refresh_from_db()
        self.assertEqual(self.postulacion.paso_actual, 2)
        self.assertEqual(self.postulacion.telefono, "+56912345678")
        self.assertTrue(self.postulacion.disponible_4x4)

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
        self.assertEqual(len(textos), 6)
        self.assertEqual(len(textos), len(set(textos)))
        tipos = [item["tipo_instalacion_nombre"] for item in response.data["preguntas"]]
        self.assertEqual({tipo: tipos.count(tipo) for tipo in set(tipos)}, {"General": 2, "Bodega": 2, "Condominio": 2})

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
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["tipo_documento"], "curriculum")
        self.assertEqual(response.data["nombre_documento"], "Currículum")
        self.assertEqual(response.status_code, 201)
        self.assertNotIn(self.postulacion.rut, upload_mock.call_args.args[1])
