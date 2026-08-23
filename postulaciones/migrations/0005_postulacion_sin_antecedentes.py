from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("postulaciones", "0004_clavetemporal_storage_compartido")]
    operations = [
        migrations.AddField(model_name="postulacionguardia", name="sin_estudios", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="postulacionguardia", name="sin_experiencia", field=models.BooleanField(default=False)),
    ]
