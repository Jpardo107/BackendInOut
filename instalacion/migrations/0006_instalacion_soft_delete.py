from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("instalacion", "0005_zona_alter_instalacion_zona")]

    operations = [
        migrations.AddField(
            model_name="instalacion",
            name="activa",
            field=models.BooleanField(db_index=True, default=True),
        ),
    ]
