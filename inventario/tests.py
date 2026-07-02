from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import serializers

from user.models import Cargo, Usuario
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
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        movimiento = serializer.save()
        prenda.refresh_from_db()

        self.assertIsNone(movimiento.usuario_final)
        self.assertEqual(movimiento.stock_despues, 3)
        self.assertEqual(prenda.stock_actual, 3)

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
