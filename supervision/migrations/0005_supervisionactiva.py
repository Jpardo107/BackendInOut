import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("instalacion", "0001_initial"),
        ("supervision", "0004_supervision_latitud_supervision_longitud"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SupervisionActiva",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fecha", models.DateField()),
                ("hora_inicio", models.TimeField()),
                ("latitud", models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ("longitud", models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ("creada_en", models.DateTimeField(auto_now_add=True)),
                ("actualizada_en", models.DateTimeField(auto_now=True)),
                ("instalacion", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="supervisiones_activas", to="instalacion.instalacion")),
                ("supervisor", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="supervision_activa", to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
