from collections import Counter
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from inventario.models import MovimientoInventario
from reportes.models import ReporteInforme
from supervision.models import Supervision, RendicionGasto
from vehiculos.models import MovimientoVehiculo
from .models import Actividad, DiaEspecial, Pauta, TIPOS

LABELS = dict(TIPOS + [("extra", "Turno extra")])
SOURCES = {
    "supervision": (Supervision, "supervisor"),
    "inventario": (MovimientoInventario, "usuario_registro"),
    "informe": (ReporteInforme, "usuario_creador"),
    "gasto": (RendicionGasto, "supervisor"),
    "vehiculo": (MovimientoVehiculo, "supervisor"),
}


def registro_pertenece(user, ref):
    try:
        source, pk = ref.split(":")
        model, owner = SOURCES[source]
        query = model.objects.filter(pk=int(pk), **{owner: user})
        return query.exists()
    except (ValueError, KeyError):
        return False


def calendario(user, desde, hasta):
    pautas = list(Pauta.objects.filter(usuario=user, inicio__lte=hasta))
    especiales = {d.fecha: d for d in DiaEspecial.objects.filter(usuario=user, fecha__range=(desde, hasta))}
    result = []
    day = desde
    while day <= hasta:
        pauta = next((p for p in reversed(pautas) if p.inicio <= day), None)
        position = (day - pauta.inicio).days % (pauta.dias_trabajo + pauta.dias_libres) if pauta else None
        base = ("trabajo" if position < pauta.dias_trabajo else "libre") if pauta else "sin_pauta"
        override = especiales.get(day)
        kind = override.tipo if override else base
        schedule = override or pauta
        result.append({
            "fecha": day.isoformat(), "base": base, "tipo": kind,
            "pauta_id": pauta.pk if pauta else None,
            "dia_ciclo": position + 1 if pauta else None,
            "jornada": schedule.jornada if schedule and kind != "libre" else "",
            "hora_inicio": schedule.hora_inicio.strftime("%H:%M") if schedule and kind != "libre" and schedule.hora_inicio else None,
            "hora_fin": schedule.hora_fin.strftime("%H:%M") if schedule and kind != "libre" and schedule.hora_fin else None,
            "nota": override.nota if override else "",
            "especial_id": override.pk if override else None,
            "realizado": override.realizado if override else False,
        })
        day += timedelta(days=1)
    return result


def actividades(user, filters):
    desde, hasta = filters["desde"], filters["hasta"]
    tz = ZoneInfo(filters["zona"])
    lower = datetime.combine(desde, time.min, tzinfo=tz)
    upper = datetime.combine(hasta + timedelta(days=1), time.min, tzinfo=tz)
    rows = []

    def add(ref, fecha, inicio, fin, tipo, titulo, detalle="", lugar="", estado="realizada", origen="manual", url="", **extra):
        rows.append({"id": ref, "fecha": fecha.isoformat(), "hora_inicio": inicio.strftime("%H:%M") if inicio else "",
                     "hora_fin": fin.strftime("%H:%M") if fin else "", "tipo": tipo, "tipo_nombre": LABELS[tipo],
                     "titulo": titulo, "detalle": detalle or "", "lugar": lugar, "estado": estado,
                     "origen": origen, "url": url, **extra})

    for a in Actividad.objects.filter(usuario=user, fecha__range=(desde, hasta)).exclude(tipo="solicitud").exclude(registro_vinculado__startswith="solicitud:").select_related("instalacion"):
        add(f"manual:{a.pk}", a.fecha, a.hora_inicio, a.hora_fin, a.tipo, a.titulo, a.detalle,
            a.instalacion.nombre if a.instalacion else "", a.estado, registro_vinculado=a.registro_vinculado,
            actividad_id=a.pk, instalacion=a.instalacion_id)

    for s in Supervision.objects.filter(supervisor=user, fecha__range=(desde, hasta)).select_related("instalacion"):
        add(f"supervision:{s.pk}", s.fecha, s.hora_inicio, s.hora_final, "supervision", f"Supervisión · {s.instalacion.nombre}",
            s.novedades, s.instalacion.nombre, origen="Supervisiones")

    for m in MovimientoInventario.objects.filter(usuario_registro=user, creado_en__gte=lower, creado_en__lt=upper).select_related("prenda", "destinatario_personal", "usuario_final"):
        local = m.creado_en.astimezone(tz)
        person = m.destinatario_personal.nombre_completo if m.destinatario_personal else (str(m.usuario_final) if m.usuario_final else "")
        detail = " · ".join(filter(None, [person, f"Estado actual: {m.get_estado_envio_display()}", m.observacion]))
        add(f"inventario:{m.pk}", local.date(), local.time(), None, m.prenda.categoria,
            f"{m.get_tipo_display()} · {m.cantidad} × {m.prenda.nombre_prenda} ({m.prenda.talla_prenda})",
            detail, origen="Inventario", url="/inventario")

    for r in ReporteInforme.objects.filter(usuario_creador=user, creado_en__gte=lower, creado_en__lt=upper, estado="generado").select_related("instalacion"):
        local = r.creado_en.astimezone(tz)
        add(f"informe:{r.pk}", local.date(), local.time(), None, "informe", r.get_tipo_reporte_display(),
            r.descripcion_hechos, r.instalacion.nombre, origen="Informes", url="/reportes")

    for r in RendicionGasto.objects.filter(supervisor=user, creada_en__gte=lower, creada_en__lt=upper):
        local = r.creada_en.astimezone(tz)
        amount = f"${r.monto:,.0f}".replace(",", ".") if r.monto is not None else "Monto no registrado"
        add(f"gasto:{r.pk}", local.date(), local.time(), None, "gasto", f"Rendición · {amount}",
            " · ".join(filter(None, [r.persona, r.motivo])), r.instalacion, origen="Rendiciones", url="/rendicion-gastos")

    for m in MovimientoVehiculo.objects.filter(supervisor=user, creado_en__gte=lower, creado_en__lt=upper).select_related("vehiculo"):
        local = m.creado_en.astimezone(tz)
        add(f"vehiculo:{m.pk}", local.date(), local.time(), None, "vehiculo", f"{m.get_tipo_display()} de vehículo · {m.vehiculo.patente}",
            f"{m.kilometraje} km · {m.resumen}", origen="Vehículos", url="/vehiculos")

    for d in DiaEspecial.objects.filter(usuario=user, fecha__range=(desde, hasta), tipo="extra"):
        add(f"extra:{d.pk}", d.fecha, d.hora_inicio, d.hora_fin, "extra", f"Turno extra · {d.get_jornada_display()}",
            d.nota, estado="realizada" if d.realizado else "pendiente", origen="Mi pauta")

    # A linked plan stays visible in the agenda, but is never counted a second time.
    for row in rows:
        row["contabilizable"] = row["estado"] == "realizada" and not row.get("registro_vinculado")
    tipo = filters.get("tipo")
    start, end = filters.get("hora_desde"), filters.get("hora_hasta")
    def matches(row):
        if tipo and row["tipo"] != tipo:
            return False
        if start and end:
            value = time.fromisoformat(row["hora_inicio"])
            return start <= value <= end if start <= end else value >= start or value <= end
        return True
    return sorted((r for r in rows if matches(r)), key=lambda r: (r["fecha"], r["hora_inicio"], r["id"]))


def resumen(user, filters, rows):
    completed = [r for r in rows if r["contabilizable"]]
    counts = Counter(r["tipo_nombre"] for r in completed)
    fmt = lambda d: d.strftime("%d/%m/%Y")
    lines = ["📋 *RESUMEN DE ACTIVIDADES*", f"👤 {user.nombres} {user.apellidos}",
             f"📅 {fmt(filters['desde'])}" + (f" al {fmt(filters['hasta'])}" if filters['desde'] != filters['hasta'] else "")]
    if filters.get("hora_desde"):
        lines.append(f"🕒 Inicios entre {filters['hora_desde']:%H:%M} y {filters['hora_hasta']:%H:%M}" + (" (franja nocturna)" if filters['hora_desde'] > filters['hora_hasta'] else ""))
    if filters.get("tipo"):
        lines.append(f"🏷️ {LABELS[filters['tipo']]}")
    lines += ["", f"*{len(completed)} registros realizados*"]
    lines.extend(f"• {name}: {count}" for name, count in sorted(counts.items()))
    last_day = None
    for row in completed:
        if row["fecha"] != last_day:
            last_day = row["fecha"]
            lines += ["", f"*{fmt(datetime.fromisoformat(last_day))}*"]
        hours = row["hora_inicio"]
        if row["hora_fin"]:
            hours += f"–{row['hora_fin']}" + (" (+1 día)" if row['hora_fin'] < row['hora_inicio'] else "")
        lines.append(f"✓ {hours} | {row['titulo']}")
        if row["lugar"] and row["lugar"] not in row["titulo"]:
            lines.append(f"  📍 {row['lugar']}")
        if row["detalle"]:
            lines.extend(f"  {line}" for line in row["detalle"].splitlines())
    if not completed:
        lines.append("Sin actividades realizadas para estos filtros.")
    lines += ["", "_INOUT · Planificación personal_", "_Los movimientos muestran su estado actual._"]
    return {"texto": "\n".join(lines), "total": len(completed), "por_tipo": dict(counts), "registros": completed}
