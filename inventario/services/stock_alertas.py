import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

from inventario.models import ConfiguracionAlertaStock, MovimientoInventario, PrendaInventario, RegistroAlertaStock


logger = logging.getLogger(__name__)


def alcanzo_stock_critico(stock_antes, stock_despues, stock_critico):
    return stock_antes > stock_critico and stock_despues <= stock_critico


def enviar_alerta_stock(prenda_id, stock_actual, stock_critico, movimiento_id=None):
    configuracion = ConfiguracionAlertaStock.objects.first()
    destinatarios = configuracion.destinatarios if configuracion else []
    prenda = PrendaInventario.objects.get(id=prenda_id)
    movimiento = MovimientoInventario.objects.filter(id=movimiento_id).first() if movimiento_id else None
    registro = RegistroAlertaStock.objects.create(
        prenda=prenda,
        movimiento=movimiento,
        stock_actual=stock_actual,
        stock_critico=stock_critico,
        destinatarios=destinatarios,
    )

    if not destinatarios:
        registro.error = "No existen destinatarios configurados."
        registro.save(update_fields=["error"])
        return registro

    subject = f"ALERTA DE STOCK: {prenda.nombre_prenda} / {prenda.talla_prenda}"
    text = (
        "Alerta de stock crítico INOUT\n\n"
        f"Prenda: {prenda.nombre_prenda}\n"
        f"Talla: {prenda.talla_prenda}\n"
        f"Stock actual: {stock_actual}\n"
        f"Stock mínimo configurado: {stock_critico}\n\n"
        "El inventario alcanzó o quedó bajo el nivel mínimo. Se recomienda gestionar reposición."
    )
    html = f"""
    <div style="font-family:Arial,sans-serif;color:#1f2937;max-width:620px">
      <div style="background:#193040;color:white;padding:16px 20px;font-size:18px;font-weight:bold">Alerta de stock crítico INOUT</div>
      <div style="border:1px solid #d9e2ec;padding:20px">
        <p>El siguiente artículo alcanzó o quedó bajo el stock mínimo configurado:</p>
        <table style="width:100%;border-collapse:collapse">
          <tr><td style="padding:8px;background:#eef2f7;font-weight:bold">Prenda</td><td style="padding:8px">{prenda.nombre_prenda}</td></tr>
          <tr><td style="padding:8px;background:#eef2f7;font-weight:bold">Talla</td><td style="padding:8px">{prenda.talla_prenda}</td></tr>
          <tr><td style="padding:8px;background:#eef2f7;font-weight:bold">Stock actual</td><td style="padding:8px;color:#b42318;font-weight:bold">{stock_actual}</td></tr>
          <tr><td style="padding:8px;background:#eef2f7;font-weight:bold">Stock mínimo</td><td style="padding:8px">{stock_critico}</td></tr>
        </table>
        <p style="margin-top:18px">Se recomienda gestionar la reposición de inventario.</p>
      </div>
    </div>
    """

    try:
        message = EmailMultiAlternatives(
            subject=subject,
            body=text,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            to=destinatarios,
        )
        message.attach_alternative(html, "text/html")
        message.send(fail_silently=False)
        registro.enviado = True
        registro.save(update_fields=["enviado"])
    except Exception as exc:
        logger.exception("No se pudo enviar alerta de stock para prenda %s", prenda_id)
        registro.error = str(exc)[:1000]
        registro.save(update_fields=["error"])
    return registro
