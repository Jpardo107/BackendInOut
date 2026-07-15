from django.core.files.uploadedfile import SimpleUploadedFile
from django.core import mail
from django.test import TestCase, override_settings
from unittest.mock import patch

from rest_framework.test import APIClient
from rest_framework import serializers

from user.models import Cargo, PersonalEmpresa, Usuario
from .models import AutorizacionEntregaInventario, ConfiguracionAlertaStock, MovimientoInventario, PrendaInventario, RegistroAlertaStock
from .serializers import MovimientoInventarioSerializer, PrendaInventarioSerializer


class PrendaInventarioTests(TestCase):
    def setUp(self):
        cargo = Cargo.objects.create(nombre="Administrador")
        self.admin_user = Usuario.objects.create_user(
            username="admin.inventario",
            password="test-pass",
            nombres="Admin",
            apellidos="Inventario",
            rut="22222222-2",
            email="admin.inventario@example.com",
            cargo=cargo,
            is_staff=True,
        )

    def test_no_permite_prenda_talla_duplicada_normalizada(self):
        PrendaInventario.objects.create(
            nombre_prenda="POLAR HOMBRE",
            talla_prenda="XL",
            cantidad_prenda=3,
            stock_actual=3,
        )

        serializer = PrendaInventarioSerializer(
            data={
                "nombre_prenda": " polar   hombre ",
                "talla_prenda": "xl",
                "cantidad_prenda": 2,
                "stock_actual": 2,
                "stock_critico": 1,
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("detail", serializer.errors)

    def test_genera_codigos_desde_nombre_y_talla(self):
        prenda = PrendaInventario.objects.create(
            nombre_prenda="Pantalon Hombre",
            talla_prenda="44",
            cantidad_prenda=4,
            stock_actual=4,
        )

        self.assertEqual(prenda.codigo_barra, "INV-PANTALON-HOMBRE-44")
        self.assertEqual(prenda.codigo_qr, "inout://inventario/prenda/INV-PANTALON-HOMBRE-44")

    def test_permite_mismo_nombre_en_categorias_distintas(self):
        PrendaInventario.objects.create(nombre_prenda="RADIO", talla_prenda="UNICA")
        serializer = PrendaInventarioSerializer(data={
            "categoria": PrendaInventario.CATEGORIA_CARGO_FIJO,
            "nombre_prenda": "RADIO",
            "talla_prenda": "UNICA",
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_buscar_codigo_resuelve_barra_qr_y_segmento_final(self):
        prenda = PrendaInventario.objects.create(
            nombre_prenda="Pantalon Hombre",
            talla_prenda="44",
            cantidad_prenda=4,
            stock_actual=4,
        )
        client = APIClient()
        client.force_authenticate(user=self.admin_user)

        for codigo in [prenda.codigo_barra, prenda.codigo_qr, "INV-PANTALON-HOMBRE-44"]:
            response = client.get("/api/inventario/prendas/buscar-codigo/", {"codigo": codigo})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["id"], prenda.id)

    def test_elimina_configuracion_sin_entregas(self):
        prenda = PrendaInventario.objects.create(nombre_prenda="CHAQUETA", talla_prenda="M")
        client = APIClient()
        client.force_authenticate(user=self.admin_user)
        response = client.post(f"/api/inventario/prendas/{prenda.id}/eliminar-configuracion/")
        self.assertEqual(response.status_code, 204)
        prenda.refresh_from_db()
        self.assertFalse(prenda.activo)

    def test_no_elimina_configuracion_con_entregas(self):
        prenda = PrendaInventario.objects.create(nombre_prenda="CHAQUETA", talla_prenda="L", stock_actual=2)
        MovimientoInventario.objects.create(
            prenda=prenda, tipo=MovimientoInventario.TIPO_ENTREGA, cantidad=1,
            stock_antes=2, stock_despues=1, observacion="Operaciones",
        )
        client = APIClient()
        client.force_authenticate(user=self.admin_user)
        response = client.post(f"/api/inventario/prendas/{prenda.id}/eliminar-configuracion/")
        self.assertEqual(response.status_code, 400)
        prenda.refresh_from_db()
        self.assertTrue(prenda.activo)


class MovimientoInventarioTests(TestCase):
    def setUp(self):
        cargo = Cargo.objects.create(nombre="Guardia")
        self.usuario_final = Usuario.objects.create_user(
            username="guardia.test",
            password="test-pass",
            nombres="Guardia",
            apellidos="Test",
            rut="11111111-1",
            email="guardia.test@example.com",
            cargo=cargo,
        )
        self.destinatario = PersonalEmpresa.objects.create(
            rut="123456789",
            nombre_completo="GUARDIA DESTINATARIO",
            ubicacion="INSTALACION TEST",
        )

    def test_entrega_descuenta_stock(self):
        prenda = PrendaInventario.objects.create(
            nombre_prenda="CAMISA",
            talla_prenda="M",
            cantidad_prenda=5,
            stock_actual=5,
        )

        serializer = MovimientoInventarioSerializer(
            data={
                "prenda": prenda.id,
                "tipo": MovimientoInventario.TIPO_ENTREGA,
                "cantidad": 2,
                "usuario_final": None,
            }
        )

        self.assertFalse(serializer.is_valid())

    def test_entrega_a_operaciones_permite_usuario_final_vacio(self):
        prenda = PrendaInventario.objects.create(
            nombre_prenda="CAMISA",
            talla_prenda="L",
            cantidad_prenda=5,
            stock_actual=5,
        )

        serializer = MovimientoInventarioSerializer(
            data={
                "prenda": prenda.id,
                "tipo": MovimientoInventario.TIPO_ENTREGA,
                "cantidad": 2,
                "observacion": "Operaciones",
                "destinatario_personal": self.destinatario.id,
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        movimiento = serializer.save()
        prenda.refresh_from_db()

        self.assertIsNone(movimiento.usuario_final)
        self.assertEqual(movimiento.destinatario_personal, self.destinatario)
        self.assertEqual(movimiento.estado_envio, MovimientoInventario.ESTADO_EN_TRANSITO)
        self.assertEqual(movimiento.stock_despues, 3)
        self.assertEqual(prenda.stock_actual, 3)

    def test_entrega_directa_permite_usuario_final_vacio_con_destinatario(self):
        prenda = PrendaInventario.objects.create(
            nombre_prenda="PANTALON",
            talla_prenda="42",
            cantidad_prenda=5,
            stock_actual=5,
        )

        serializer = MovimientoInventarioSerializer(
            data={
                "prenda": prenda.id,
                "tipo": MovimientoInventario.TIPO_ENTREGA,
                "cantidad": 1,
                "observacion": "Entrega directa a solicitante",
                "destinatario_personal": self.destinatario.id,
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        movimiento = serializer.save()
        prenda.refresh_from_db()

        self.assertIsNone(movimiento.usuario_final)
        self.assertEqual(movimiento.destinatario_personal, self.destinatario)
        self.assertEqual(movimiento.estado_envio, MovimientoInventario.ESTADO_EN_TRANSITO)
        self.assertEqual(prenda.stock_actual, 4)

    def test_entrega_recibida_no_modifica_stock(self):
        cargo_supervisor = Cargo.objects.create(nombre="Supervisor")
        supervisor = Usuario.objects.create_user(
            username="supervisor.test",
            password="test-pass",
            nombres="Supervisor",
            apellidos="Test",
            rut="33333333-3",
            email="supervisor.test@example.com",
            cargo=cargo_supervisor,
        )
        AutorizacionEntregaInventario.objects.create(usuario=supervisor, autorizado=True)
        prenda = PrendaInventario.objects.create(
            nombre_prenda="CAMISA",
            talla_prenda="L",
            cantidad_prenda=5,
            stock_actual=5,
        )
        movimiento = MovimientoInventarioSerializer(
            data={
                "prenda": prenda.id,
                "tipo": MovimientoInventario.TIPO_ENTREGA,
                "cantidad": 2,
                "usuario_final": supervisor.id,
            }
        )
        self.assertTrue(movimiento.is_valid(), movimiento.errors)
        entrega = movimiento.save()
        prenda.refresh_from_db()
        self.assertEqual(prenda.stock_actual, 3)

        client = APIClient()
        client.force_authenticate(user=supervisor)
        response = client.patch(
            f"/api/inventario/movimientos/{entrega.id}/cambiar-estado/",
            {"estado_envio": MovimientoInventario.ESTADO_RECIBIDO},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        entrega.refresh_from_db()
        prenda.refresh_from_db()
        self.assertEqual(entrega.estado_envio, MovimientoInventario.ESTADO_RECIBIDO)
        self.assertEqual(prenda.stock_actual, 3)

    def test_supervisor_puede_marcar_como_recibida_entrega_asignada(self):
        cargo_supervisor = Cargo.objects.create(nombre="Supervisor")
        supervisor = Usuario.objects.create_user(
            username="supervisor.asignado",
            password="test-pass",
            nombres="Supervisor",
            apellidos="Asignado",
            rut="55555555-5",
            email="supervisor.asignado@example.com",
            cargo=cargo_supervisor,
        )
        AutorizacionEntregaInventario.objects.create(usuario=supervisor, autorizado=True)
        prenda = PrendaInventario.objects.create(
            nombre_prenda="POLERA",
            talla_prenda="M",
            cantidad_prenda=3,
            stock_actual=3,
        )
        serializer = MovimientoInventarioSerializer(
            data={
                "prenda": prenda.id,
                "tipo": MovimientoInventario.TIPO_ENTREGA,
                "cantidad": 1,
                "usuario_final": supervisor.id,
                "destinatario_personal": self.destinatario.id,
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        entrega = serializer.save()

        client = APIClient()
        client.force_authenticate(user=supervisor)
        response = client.patch(
            f"/api/inventario/movimientos/{entrega.id}/cambiar-estado/",
            {
                "estado_envio": MovimientoInventario.ESTADO_RECIBIDO,
                "observacion": "Entregado con firma",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        entrega.refresh_from_db()
        self.assertEqual(entrega.estado_envio, MovimientoInventario.ESTADO_RECIBIDO)

    def test_cambiar_estado_es_idempotente_si_estado_ya_fue_aplicado(self):
        cargo_supervisor = Cargo.objects.create(nombre="Supervisor")
        supervisor = Usuario.objects.create_user(
            username="supervisor.idempotente",
            password="test-pass",
            nombres="Supervisor",
            apellidos="Idempotente",
            rut="66666666-6",
            email="supervisor.idempotente@example.com",
            cargo=cargo_supervisor,
        )
        AutorizacionEntregaInventario.objects.create(usuario=supervisor, autorizado=True)
        prenda = PrendaInventario.objects.create(
            nombre_prenda="CHAQUETA",
            talla_prenda="L",
            cantidad_prenda=2,
            stock_actual=2,
        )
        serializer = MovimientoInventarioSerializer(
            data={
                "prenda": prenda.id,
                "tipo": MovimientoInventario.TIPO_ENTREGA,
                "cantidad": 1,
                "usuario_final": supervisor.id,
                "destinatario_personal": self.destinatario.id,
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        entrega = serializer.save()

        client = APIClient()
        client.force_authenticate(user=supervisor)
        for _ in range(2):
            response = client.patch(
                f"/api/inventario/movimientos/{entrega.id}/cambiar-estado/",
                {"estado_envio": MovimientoInventario.ESTADO_RECIBIDO},
                format="json",
            )
            self.assertEqual(response.status_code, 200)

        entrega.refresh_from_db()
        self.assertEqual(entrega.estado_envio, MovimientoInventario.ESTADO_RECIBIDO)

    def test_autorizacion_entrega_requiere_encargado_rrhh_reautenticado(self):
        cargo_rrhh = Cargo.objects.create(nombre="Encargado RRHH")
        encargado = Usuario.objects.create_user(
            username="rrhh.encargado",
            password="test-pass",
            nombres="RRHH",
            apellidos="Encargado",
            rut="99999999-9",
            email="rrhh.encargado@example.com",
            cargo=cargo_rrhh,
        )
        cargo_gerente = Cargo.objects.create(nombre="Gerente de Operaciones")
        gerente = Usuario.objects.create_user(
            username="gerente.autorizable",
            password="test-pass",
            nombres="Supervisor",
            apellidos="Autorizable",
            rut="10101010-1",
            email="supervisor.autorizable@example.com",
            cargo=cargo_gerente,
        )

        client = APIClient()
        client.force_authenticate(user=encargado)
        response = client.post(
            "/api/inventario/autorizados-entrega/",
            {
                "usuario": gerente.id,
                "autorizado": True,
                "password": "test-pass",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            AutorizacionEntregaInventario.objects.get(usuario=gerente).autorizado
        )

    def test_lista_autorizados_muestra_rrhh_obligatorio_y_supervisor(self):
        cargo_rrhh = Cargo.objects.create(nombre="Administrativo RRHH")
        rrhh = Usuario.objects.create_user(
            username="rrhh.visible",
            password="test-pass",
            nombres="RRHH",
            apellidos="Visible",
            rut="13131313-1",
            email="rrhh.visible@example.com",
            cargo=cargo_rrhh,
        )
        cargo_supervisor = Cargo.objects.create(nombre="Supervisor")
        supervisor = Usuario.objects.create_user(
            username="supervisor.visible",
            password="test-pass",
            nombres="Supervisor",
            apellidos="Visible",
            rut="14141414-1",
            email="supervisor.visible@example.com",
            cargo=cargo_supervisor,
        )

        client = APIClient()
        client.force_authenticate(user=rrhh)
        response = client.get("/api/inventario/autorizados-entrega/")

        self.assertEqual(response.status_code, 200)
        usuarios = {item["username"]: item for item in response.data}
        self.assertIn(rrhh.username, usuarios)
        self.assertIn(supervisor.username, usuarios)
        self.assertTrue(usuarios[rrhh.username]["autorizado"])
        self.assertTrue(usuarios[rrhh.username]["obligatorio"])
        self.assertFalse(usuarios[rrhh.username]["editable"])

    def test_supervisor_puede_marcar_entrega_recibida_por_su_cargo(self):
        cargo_supervisor = Cargo.objects.create(nombre="Supervisor")
        supervisor = Usuario.objects.create_user(
            username="supervisor.sin.autorizacion",
            password="test-pass",
            nombres="Supervisor",
            apellidos="Sin Autorizacion",
            rut="12121212-1",
            email="supervisor.sin.autorizacion@example.com",
            cargo=cargo_supervisor,
        )
        prenda = PrendaInventario.objects.create(
            nombre_prenda="PARKA",
            talla_prenda="XL",
            cantidad_prenda=1,
            stock_actual=1,
        )
        serializer = MovimientoInventarioSerializer(
            data={
                "prenda": prenda.id,
                "tipo": MovimientoInventario.TIPO_ENTREGA,
                "cantidad": 1,
                "usuario_final": supervisor.id,
                "destinatario_personal": self.destinatario.id,
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        entrega = serializer.save()

        client = APIClient()
        client.force_authenticate(user=supervisor)
        response = client.patch(
            f"/api/inventario/movimientos/{entrega.id}/cambiar-estado/",
            {"estado_envio": MovimientoInventario.ESTADO_RECIBIDO},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        entrega.refresh_from_db()
        self.assertEqual(entrega.estado_envio, MovimientoInventario.ESTADO_RECIBIDO)

    @patch("inventario.views.upload_document")
    def test_crea_comprobante_entrega_asociado_a_movimientos(self, upload_mock):
        cargo_supervisor = Cargo.objects.create(nombre="Supervisor")
        supervisor = Usuario.objects.create_user(
            username="supervisor.comprobante",
            password="test-pass",
            nombres="Supervisor",
            apellidos="Comprobante",
            rut="77777777-7",
            email="supervisor.comprobante@example.com",
            cargo=cargo_supervisor,
        )
        prenda = PrendaInventario.objects.create(
            nombre_prenda="CAMISA",
            talla_prenda="M",
            cantidad_prenda=2,
            stock_actual=2,
        )
        serializer = MovimientoInventarioSerializer(
            data={
                "prenda": prenda.id,
                "tipo": MovimientoInventario.TIPO_ENTREGA,
                "cantidad": 1,
                "usuario_final": supervisor.id,
                "destinatario_personal": self.destinatario.id,
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        entrega = serializer.save()

        client = APIClient()
        client.force_authenticate(user=supervisor)
        archivo = SimpleUploadedFile(
            "comprobante.pdf",
            b"%PDF-1.4 comprobante",
            content_type="application/pdf",
        )
        response = client.post(
            "/api/inventario/comprobantes-entrega/",
            {"movimientos": f"[{entrega.id}]", "archivo": archivo},
            format="multipart",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["movimientos_ids"], [entrega.id])
        self.assertTrue(upload_mock.called)
        self.assertEqual(entrega.comprobantes_entrega.count(), 1)

    @patch("inventario.views.generate_signed_url", return_value="https://r2.test/comprobante.pdf")
    def test_descarga_comprobante_entrega_retorna_url_firmada(self, signed_url_mock):
        cargo_supervisor = Cargo.objects.create(nombre="Supervisor")
        supervisor = Usuario.objects.create_user(
            username="supervisor.descarga",
            password="test-pass",
            nombres="Supervisor",
            apellidos="Descarga",
            rut="88888888-8",
            email="supervisor.descarga@example.com",
            cargo=cargo_supervisor,
        )
        prenda = PrendaInventario.objects.create(
            nombre_prenda="POLAR",
            talla_prenda="L",
            cantidad_prenda=1,
            stock_actual=1,
        )
        serializer = MovimientoInventarioSerializer(
            data={
                "prenda": prenda.id,
                "tipo": MovimientoInventario.TIPO_ENTREGA,
                "cantidad": 1,
                "usuario_final": supervisor.id,
                "destinatario_personal": self.destinatario.id,
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        entrega = serializer.save()
        comprobante = entrega.comprobantes_entrega.model.objects.create(
            destinatario_personal=self.destinatario,
            supervisor=supervisor,
            storage_key="inventario/comprobantes/test.pdf",
            nombre_original="test.pdf",
            mime_type="application/pdf",
            size=100,
        )
        comprobante.movimientos.add(entrega)

        client = APIClient()
        client.force_authenticate(user=supervisor)
        response = client.get(f"/api/inventario/comprobantes-entrega/{comprobante.id}/descargar/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["url"], "https://r2.test/comprobante.pdf")
        self.assertTrue(signed_url_mock.called)

    def test_entrega_devuelta_repone_stock_y_crea_recepcion(self):
        cargo_supervisor = Cargo.objects.create(nombre="Supervisor")
        supervisor = Usuario.objects.create_user(
            username="supervisor.devolucion",
            password="test-pass",
            nombres="Supervisor",
            apellidos="Devolucion",
            rut="44444444-4",
            email="supervisor.devolucion@example.com",
            cargo=cargo_supervisor,
        )
        prenda = PrendaInventario.objects.create(
            nombre_prenda="ZAPATO",
            talla_prenda="42",
            cantidad_prenda=5,
            stock_actual=5,
        )
        serializer = MovimientoInventarioSerializer(
            data={
                "prenda": prenda.id,
                "tipo": MovimientoInventario.TIPO_ENTREGA,
                "cantidad": 2,
                "usuario_final": supervisor.id,
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        entrega = serializer.save()
        prenda.refresh_from_db()
        self.assertEqual(prenda.stock_actual, 3)

        client = APIClient()
        client.force_authenticate(user=supervisor)
        response = client.patch(
            f"/api/inventario/movimientos/{entrega.id}/cambiar-estado/",
            {
                "estado_envio": MovimientoInventario.ESTADO_DEVUELTO,
                "observacion": "Talla incorrecta",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        entrega.refresh_from_db()
        prenda.refresh_from_db()
        self.assertEqual(entrega.estado_envio, MovimientoInventario.ESTADO_DEVUELTO)
        self.assertEqual(prenda.stock_actual, 5)
        self.assertTrue(
            MovimientoInventario.objects.filter(
                tipo=MovimientoInventario.TIPO_RECEPCION,
                prenda=prenda,
                cantidad=2,
                stock_antes=3,
                stock_despues=5,
            ).exists()
        )

    def test_ingreso_suma_stock(self):
        prenda = PrendaInventario.objects.create(
            nombre_prenda="CAMISA",
            talla_prenda="M",
            cantidad_prenda=5,
            stock_actual=5,
        )

        serializer = MovimientoInventarioSerializer(
            data={
                "prenda": prenda.id,
                "tipo": MovimientoInventario.TIPO_INGRESO,
                "cantidad": 3,
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        movimiento = serializer.save()
        prenda.refresh_from_db()

        self.assertEqual(movimiento.stock_antes, 5)
        self.assertEqual(movimiento.stock_despues, 8)
        self.assertEqual(prenda.stock_actual, 8)

    def test_no_permite_entrega_sin_stock_suficiente(self):
        prenda = PrendaInventario.objects.create(
            nombre_prenda="ZAPATO",
            talla_prenda="42",
            cantidad_prenda=1,
            stock_actual=1,
        )

        serializer = MovimientoInventarioSerializer(
            data={
                "prenda": prenda.id,
                "tipo": MovimientoInventario.TIPO_ENTREGA,
                "cantidad": 2,
                "usuario_final": self.usuario_final.id,
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

        with self.assertRaises(serializers.ValidationError):
            serializer.save()

    def test_registro_manual_crea_entrega_informativa_sin_descontar_stock(self):
        cargo_admin = Cargo.objects.create(nombre="Administrador")
        admin = Usuario.objects.create_user(
            username="admin.manual",
            password="test-pass",
            nombres="Admin",
            apellidos="Manual",
            rut="15151515-1",
            email="admin.manual@example.com",
            cargo=cargo_admin,
            is_staff=True,
        )
        prenda = PrendaInventario.objects.create(
            nombre_prenda="CAMISA",
            talla_prenda="M",
            cantidad_prenda=5,
            stock_actual=5,
        )

        client = APIClient()
        client.force_authenticate(user=admin)
        response = client.post(
            "/api/inventario/movimientos/registro-manual/",
            {
                "prenda": prenda.id,
                "destinatario_personal": self.destinatario.id,
                "cantidad": 2,
                "fecha_entrega": "2025-04-15",
                "observacion": "Planilla historica",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["estado_envio"], MovimientoInventario.ESTADO_RECIBIDO)
        self.assertEqual(response.data["destinatario_personal"], self.destinatario.id)
        self.assertEqual(response.data["stock_antes"], 5)
        self.assertEqual(response.data["stock_despues"], 5)
        self.assertEqual(response.data["usuario_registro"], admin.id)
        self.assertEqual(response.data["usuario_registro_nombre"], "Admin Manual")
        self.assertIn("2025-04-15", response.data["creado_en"])
        self.assertIn("Ingreso manual informativo sin firma", response.data["observacion"])
        prenda.refresh_from_db()
        self.assertEqual(prenda.stock_actual, 5)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", DEFAULT_FROM_EMAIL="alertas@inout.cl")
    def test_envia_correo_una_vez_al_cruzar_stock_minimo(self):
        ConfiguracionAlertaStock.objects.create(email_1="compras@inout.cl", email_2="rrhh@inout.cl")
        prenda = PrendaInventario.objects.create(
            nombre_prenda="POLAR MUJER", talla_prenda="M", cantidad_prenda=7, stock_actual=7, stock_critico=5,
        )
        serializer = MovimientoInventarioSerializer(
            data={
                "prenda": prenda.id,
                "tipo": MovimientoInventario.TIPO_ENTREGA,
                "cantidad": 2,
                "usuario_final": self.usuario_final.id,
                "destinatario_personal": self.destinatario.id,
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

        with self.captureOnCommitCallbacks(execute=True):
            serializer.save()

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(set(mail.outbox[0].to), {"compras@inout.cl", "rrhh@inout.cl"})
        self.assertIn("POLAR MUJER", mail.outbox[0].subject)
        registro = RegistroAlertaStock.objects.get()
        self.assertTrue(registro.enviado)
        self.assertEqual(registro.stock_actual, 5)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_HOST="smtp.example.com",
        EMAIL_HOST_USER="alertas@example.com",
        DEFAULT_FROM_EMAIL="alertas@example.com",
    )
    @patch("inventario.views.EmailMultiAlternatives.send", return_value=1)
    def test_administrador_puede_enviar_correo_de_prueba(self, send_mock):
        cargo_admin = Cargo.objects.create(nombre="Administrador alertas")
        admin = Usuario.objects.create_user(
            username="admin.alertas",
            password="test-pass",
            nombres="Admin",
            apellidos="Alertas",
            rut="18181818-1",
            email="admin.alertas@example.com",
            cargo=cargo_admin,
            is_staff=True,
        )
        ConfiguracionAlertaStock.objects.create(email_1="compras@inout.cl")
        client = APIClient()
        client.force_authenticate(user=admin)

        response = client.post("/api/inventario/configuracion-alertas-stock/", {}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["destinatarios"], ["compras@inout.cl"])
        self.assertTrue(response.data["diagnostico_correo"]["entrega_real"])
        send_mock.assert_called_once_with(fail_silently=False)

    def test_configuracion_informa_el_ultimo_intento_de_alerta(self):
        cargo_admin = Cargo.objects.create(nombre="Administrador inventario")
        admin = Usuario.objects.create_user(
            username="admin.estado.alerta",
            password="test-pass",
            nombres="Admin",
            apellidos="Estado",
            rut="19191919-1",
            email="admin.estado@example.com",
            cargo=cargo_admin,
            is_staff=True,
        )
        ConfiguracionAlertaStock.objects.create(email_1="compras@inout.cl")
        prenda = PrendaInventario.objects.create(
            nombre_prenda="PARKA", talla_prenda="L", cantidad_prenda=5, stock_actual=5, stock_critico=5,
        )
        RegistroAlertaStock.objects.create(
            prenda=prenda,
            stock_actual=5,
            stock_critico=5,
            destinatarios=["compras@inout.cl"],
            error="SMTP no disponible",
        )
        client = APIClient()
        client.force_authenticate(user=admin)

        response = client.get("/api/inventario/configuracion-alertas-stock/")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["ultimo_intento"]["enviado"])
        self.assertEqual(response.data["ultimo_intento"]["error"], "SMTP no disponible")
