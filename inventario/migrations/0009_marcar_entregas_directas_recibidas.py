from django.db import migrations


def marcar_entregas_directas_recibidas(apps, schema_editor):
    MovimientoInventario = apps.get_model("inventario", "MovimientoInventario")
    MovimientoInventario.objects.filter(
        tipo="entrega",
        observacion__iexact="Entrega directa a solicitante",
        estado_envio="en_transito",
    ).update(estado_envio="recibido")


class Migration(migrations.Migration):
    dependencies = [
        ("inventario", "0008_alter_prendainventario_categoria"),
    ]

    operations = [
        migrations.RunPython(
            marcar_entregas_directas_recibidas,
            migrations.RunPython.noop,
        ),
    ]
