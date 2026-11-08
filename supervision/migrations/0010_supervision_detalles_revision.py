from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("supervision", "0009_rendicion_deposito")]

    operations = [
        migrations.AddField(
            model_name="supervision",
            name="detalles_revision",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
