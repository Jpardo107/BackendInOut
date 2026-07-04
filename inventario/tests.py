from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import serializers

from user.models import Cargo, PersonalEmpresa, Usuario
from .models import MovimientoInventario, PrendaInventario
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
