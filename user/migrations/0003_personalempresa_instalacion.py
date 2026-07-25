from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("instalacion", "0005_zona_alter_instalacion_zona"),
        ("user", "0002_personalempresa"),
    ]

    operations = [
        migrations.AddField(
            model_name="personalempresa",
            name="instalacion",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="personal",
                to="instalacion.instalacion",
            ),
        ),
    ]
