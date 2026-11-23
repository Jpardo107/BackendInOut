from django.db import migrations
from django.db.models import Count


def limpiar_creada_en_retroactivo(apps, schema_editor):
    """La 0011 dejó a todas las supervisiones existentes con la hora de la migración en creada_en.

    Esas filas comparten exactamente el mismo valor (el de la supervisión más antigua). Se dejan en
    null para que el resumen de solicitudes use su fecha + hora_final reales.
    """
    Supervision = apps.get_model("supervision", "Supervision")
    primera = Supervision.objects.exclude(creada_en__isnull=True).order_by("id").first()
    if not primera:
        return
    repetidas = Supervision.objects.filter(creada_en=primera.creada_en)
    if repetidas.aggregate(total=Count("id"))["total"] > 1:
        repetidas.update(creada_en=None)


class Migration(migrations.Migration):
    dependencies = [
        ("supervision", "0011_resumen_solicitudes"),
    ]

    operations = [
        migrations.RunPython(limpiar_creada_en_retroactivo, migrations.RunPython.noop),
    ]
