from datetime import date, datetime, time, timezone
import uuid
from reportes.models import ReporteInforme
from vehiculos.models import Vehiculo, MovimientoVehiculo
from django.test import TestCase
from rest_framework.test import APIClient
from instalacion.models import Instalacion
from inventario.models import MovimientoInventario, PrendaInventario
from supervision.models import Supervision, RendicionGasto
from user.models import Usuario
from .models import Actividad, DiaEspecial, Pauta
from .services import calendario


class PlanificacionTests(TestCase):
    def setUp(self):
        self.jaime = Usuario.objects.create_user(username="jaime.plan", rut="17.511.942-6", nombres="Jaime", apellidos="Pardo", email="jaime@example.com")
        self.other = Usuario.objects.create_user(username="otro.plan", rut="11111111-1", nombres="Jaime", apellidos="Pardo", email="otro@example.com", is_superuser=True)
        self.client = APIClient()
        self.client.force_authenticate(self.jaime)
        self.installation = Instalacion.objects.create(nombre="Planta Norte", direccion="Ruta 5", comuna="Lampa", nombre_contacto="Contacto", correo_contacto="test@example.com", telefono_contacto="123")
        self.payload = {"fecha": "2026-10-25", "hora_inicio": "08:00", "hora_fin": "08:30", "tipo": "coordinacion", "titulo": "Coordinar reemplazo", "estado": "pendiente"}

    def panel(self, **kwargs):
        params = {"desde": "2026-10-25", "hasta": "2026-10-25", "zona": "America/Santiago", **kwargs}
        response = self.client.get("/api/planificacion/panel/", params)
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def supervision(self, owner=None, **kwargs):
        return Supervision.objects.create(supervisor=owner or self.jaime, instalacion=self.installation, fecha=date(2026, 10, 25), hora_inicio=time(9, 17), hora_final=time(9, 48), novedades="Todo revisado", **kwargs)

    def pauta(self, **kwargs):
        return Pauta.objects.create(usuario=self.jaime, inicio=date(2026, 10, 25), dias_trabajo=4, dias_libres=4, jornada="diurna", hora_inicio=time(8), hora_fin=time(20), **kwargs)

    def test_owner_only_even_another_admin_with_same_name(self):
        for user in (None, self.other):
            self.client.force_authenticate(user)
            for path in ("panel/", "opciones/", "pautas/", "dias/", "actividades/"):
                self.assertIn(self.client.get(f"/api/planificacion/{path}").status_code, (401, 403))
                self.assertIn(self.client.post(f"/api/planificacion/{path}", self.payload).status_code, (401, 403))
        self.client.force_authenticate(self.jaime)
        self.assertEqual(self.client.get("/api/planificacion/opciones/").status_code, 200)

    def test_inactive_owner_denied(self):
        self.jaime.is_active = False
        self.assertEqual(self.client.get("/api/planificacion/opciones/").status_code, 403)

    def test_create_edit_complete_delete_activity_and_owner_cannot_be_spoofed(self):
        response = self.client.post("/api/planificacion/actividades/", {**self.payload, "usuario": self.other.pk}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        pk = response.data["id"]
        self.assertEqual(Actividad.objects.get(pk=pk).usuario, self.jaime)
        self.assertEqual(self.panel()["resumen"]["total"], 0)
        response = self.client.patch(f"/api/planificacion/actividades/{pk}/", {"estado": "realizada", "detalle": "Reemplazo confirmado"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Reemplazo confirmado", self.panel()["resumen"]["texto"])
        self.assertEqual(self.client.delete(f"/api/planificacion/actividades/{pk}/").status_code, 204)

    def test_cross_owner_ids_not_readable_or_writable(self):
        activity = Actividad.objects.create(usuario=self.other, **self.payload)
        for method in ("get", "patch", "delete"):
            self.assertEqual(getattr(self.client, method)(f"/api/planificacion/actividades/{activity.pk}/").status_code, 404)
        self.assertEqual(self.panel()["resumen"]["total"], 0)

    def test_manual_times_reject_other_minutes_seconds_and_equal_times(self):
        for value in ("08:15", "08:30:01", "08:30"):
            response = self.client.post("/api/planificacion/actividades/", {**self.payload, "hora_inicio": value}, format="json")
            self.assertEqual(response.status_code, 400, response.data)
        response = self.client.post("/api/planificacion/actividades/", {**self.payload, "hora_inicio": "23:30", "hora_fin": "00:30", "estado": "realizada"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIn("(+1 día)", self.panel()["resumen"]["texto"])

    def test_cycle_rest_extra_and_next_free(self):
        self.pauta()
        days = calendario(self.jaime, date(2026, 10, 24), date(2026, 11, 2))
        self.assertEqual([d["tipo"] for d in days], ["sin_pauta"] + ["trabajo"] * 4 + ["libre"] * 4 + ["trabajo"])
        self.assertEqual(self.panel()["proximo_libre"], "2026-10-29")
        response = self.client.post("/api/planificacion/dias/", {"fecha": "2026-10-29", "tipo": "extra", "jornada": "nocturna", "hora_inicio": "20:00", "hora_fin": "08:00"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.panel()["proximo_libre"], "2026-10-30")
        self.assertEqual(self.panel(desde="2026-10-29", hasta="2026-10-29")["resumen"]["total"], 0)
        self.client.patch(f"/api/planificacion/dias/{response.data['id']}/", {"realizado": True}, format="json")
        self.assertEqual(self.panel(desde="2026-10-29", hasta="2026-10-29")["resumen"]["total"], 1)
        self.assertEqual(calendario(self.jaime, date(2026, 11, 2), date(2026, 11, 2))[0]["dia_ciclo"], 1)
        self.client.delete(f"/api/planificacion/dias/{response.data['id']}/")
        self.assertEqual(self.panel()["proximo_libre"], "2026-10-29")

    def test_pauta_versions_upsert_and_no_history_loss(self):
        self.pauta()
        data = {"inicio": "2026-11-01", "dias_trabajo": 5, "dias_libres": 2, "jornada": "am", "hora_inicio": "06:00", "hora_fin": "14:00"}
        for _ in range(2):
            response = self.client.post("/api/planificacion/pautas/", data, format="json")
            self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Pauta.objects.count(), 2)
        days = calendario(self.jaime, date(2026, 10, 31), date(2026, 11, 6))
        self.assertEqual(days[0]["tipo"], "libre")
        self.assertEqual(days[1]["dia_ciclo"], 1)
        self.assertEqual(days[-1]["tipo"], "libre")
        self.assertEqual(days[1]["jornada"], "am")

    def test_invalid_pauta_and_special(self):
        for data in ({"fecha": "2026-10-25", "tipo": "extra"}, {"fecha": "2026-10-25", "tipo": "extra", "hora_inicio": "20:15", "hora_fin": "08:00"}):
            self.assertEqual(self.client.post("/api/planificacion/dias/", data).status_code, 400)
        self.assertEqual(self.client.post("/api/planificacion/pautas/", {"inicio": "2026-10-25", "dias_trabajo": 0, "dias_libres": 4, "jornada": "pm", "hora_inicio": "14:00", "hora_fin": "20:00"}).status_code, 400)

    def test_integrated_sources_local_dates_and_actual_times(self):
        self.supervision(solicitudes="Solicitar parkas")
        self.supervision(owner=self.other, solicitudes="No mostrar")
        item = PrendaInventario.objects.create(nombre_prenda="Parka", talla_prenda="L", cantidad_prenda=5, stock_actual=3)
        movement = MovimientoInventario.objects.create(prenda=item, tipo="entrega", cantidad=2, stock_antes=5, stock_despues=3, usuario_registro=self.jaime, estado_envio="recibido")
        # 02:15 UTC Oct 26 is 23:15 Oct 25 in Chile. Must not be lost to UTC date filtering.
        MovimientoInventario.objects.filter(pk=movement.pk).update(creado_en=datetime(2026, 10, 26, 2, 15, tzinfo=timezone.utc))
        expense = RendicionGasto.objects.create(supervisor=self.jaime, supervisor_nombre="Jaime Pardo", instalacion="Planta Norte", persona="Guardia", monto=12500, motivo="Traslado", storage_key="test")
        RendicionGasto.objects.filter(pk=expense.pk).update(creada_en=datetime(2026, 10, 25, 4, tzinfo=timezone.utc))
        data = self.panel()
        self.assertEqual(data["resumen"]["total"], 3)
        self.assertIn("09:17–09:48", data["resumen"]["texto"])
        self.assertIn("23:15", data["resumen"]["texto"])
        self.assertIn("$12.500", data["resumen"]["texto"])
        self.assertNotIn("No mostrar", data["resumen"]["texto"])
        self.assertNotIn("Solicitar parkas", data["resumen"]["texto"])
        self.assertEqual(self.panel(hora_desde="20:00", hora_hasta="08:00")["resumen"]["total"], 2)
        self.assertEqual(self.panel(hora_desde="09:00", hora_hasta="10:00")["resumen"]["total"], 1)

    def test_linked_plan_counted_once_and_cannot_link_other_user(self):
        source = self.supervision()
        other_source = self.supervision(owner=self.other)
        for ref in (f"supervision:{other_source.pk}", "supervision:999999", "bad:1"):
            response = self.client.post("/api/planificacion/actividades/", {**self.payload, "estado": "realizada", "registro_vinculado": ref}, format="json")
            self.assertEqual(response.status_code, 400)
        response = self.client.post("/api/planificacion/actividades/", {**self.payload, "estado": "realizada", "registro_vinculado": f"supervision:{source.pk}"}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(self.panel()["actividades"]), 2)
        self.assertEqual(self.panel()["resumen"]["total"], 1)
        self.assertEqual(self.client.patch(f"/api/planificacion/actividades/{response.data['id']}/", {"estado": "pendiente"}, format="json").status_code, 400)

    def test_invalid_filters_and_empty_summary(self):
        for params in ({}, {"desde": "2026-10-25", "hasta": "2026-10-24"}, {"desde": "2024-01-01", "hasta": "2026-10-25"}, {"desde": "2026-10-25", "hasta": "2026-10-25", "hora_desde": "08:00"}, {"desde": "2026-10-25", "hasta": "2026-10-25", "zona": "../invalid"}, {"desde": "2026-10-25", "hasta": "2026-10-25", "tipo": "unknown"}):
            self.assertEqual(self.client.get("/api/planificacion/panel/", params).status_code, 400)
        self.assertIn("Sin actividades realizadas", self.panel()["resumen"]["texto"])

    def test_generated_reports_and_vehicle_movements_are_integrated(self):
        report = ReporteInforme.objects.create(usuario_creador=self.jaime, instalacion=self.installation,
            tipo_reporte="pre_informe", autor_nombre="Jaime Pardo", fecha_emision=date(2026, 10, 25),
            estado="generado", descripcion_hechos="Informe de novedades")
        ReporteInforme.objects.filter(pk=report.pk).update(creado_en=datetime(2026, 10, 25, 15, tzinfo=timezone.utc))
        vehicle = Vehiculo.objects.create(patente="PLAN12", marca="Prueba", modelo="Prueba")
        move = MovimientoVehiculo.objects.create(vehiculo=vehicle, supervisor=self.jaime,
            supervisor_nombre="Jaime Pardo", solicitud_id=uuid.uuid4(), tipo="recepcion", kilometraje=1000,
            gata=True, llave_cruz=True, extintor=True, triangulo=True, resumen="Sin novedades")
        MovimientoVehiculo.objects.filter(pk=move.pk).update(creado_en=datetime(2026, 10, 25, 11, tzinfo=timezone.utc))
        data = self.panel()
        self.assertEqual(data["resumen"]["total"], 2)
        self.assertIn("PLAN12", data["resumen"]["texto"])
        self.assertIn("Informe de novedades", data["resumen"]["texto"])
        report.estado = "borrador"
        report.save(update_fields=["estado"])
        self.assertEqual(self.panel()["resumen"]["total"], 1)

    def test_special_date_cannot_be_moved_onto_an_existing_day(self):
        one = DiaEspecial.objects.create(usuario=self.jaime, fecha=date(2026, 10, 25), tipo="libre")
        DiaEspecial.objects.create(usuario=self.jaime, fecha=date(2026, 10, 26), tipo="libre")
        response = self.client.patch(f"/api/planificacion/dias/{one.pk}/", {"fecha": "2026-10-26"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(DiaEspecial.objects.count(), 2)

    def test_supervision_requests_are_removed_from_planning_without_erasing_sources(self):
        source = self.supervision(solicitudes="Reponer uniformes", estado_solicitud="pendiente")
        legacy = Actividad.objects.create(usuario=self.jaime, **{**self.payload, "tipo": "solicitud", "titulo": "Solicitud anterior", "estado": "realizada"})
        linked = Actividad.objects.create(usuario=self.jaime, **{**self.payload, "titulo": "Plan vinculado anterior", "estado": "realizada", "registro_vinculado": f"solicitud:{source.pk}"})
        data = self.panel()
        self.assertEqual([r["id"] for r in data["actividades"]], [f"supervision:{source.pk}"])
        self.assertEqual(data["resumen"]["total"], 1)
        self.assertNotIn("Reponer uniformes", data["resumen"]["texto"])
        self.assertNotIn("Solicitud", data["resumen"]["texto"])
        self.assertIn("Todo revisado", data["resumen"]["texto"])
        self.assertNotIn("solicitud", [t["value"] for t in self.client.get("/api/planificacion/opciones/").data["tipos"]])
        filters = {"desde": "2026-10-25", "hasta": "2026-10-25"}
        self.assertEqual(self.client.get("/api/planificacion/actividades/", filters).data, [])
        self.assertEqual(self.client.get("/api/planificacion/panel/", {**filters, "tipo": "solicitud"}).status_code, 400)
        for extra in ({"tipo": "solicitud"}, {"registro_vinculado": f"solicitud:{source.pk}", "estado": "realizada"}):
            self.assertEqual(self.client.post("/api/planificacion/actividades/", {**self.payload, **extra}, format="json").status_code, 400)
        source.refresh_from_db()
        self.assertEqual(source.solicitudes, "Reponer uniformes")
        self.assertTrue(Actividad.objects.filter(pk=legacy.pk).exists())
        self.assertTrue(Actividad.objects.filter(pk=linked.pk).exists())
