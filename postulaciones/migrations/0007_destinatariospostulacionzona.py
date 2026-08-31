from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("instalacion", "0005_zona_alter_instalacion_zona"),
        ("postulaciones", "0006_analisis_perfil"),
    ]

    operations = [
        migrations.CreateModel(
            name="DestinatariosPostulacionZona",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("correos", models.JSONField(blank=True, default=list)),
                ("actualizado_en", models.DateTimeField(auto_now=True)),
                ("zona", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="destinatarios_postulaciones", to="instalacion.zona")),
            ],
            options={"ordering": ("zona__nombre",)},
        ),
    ]
