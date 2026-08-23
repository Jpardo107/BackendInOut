from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("postulaciones", "0003_alter_documentopostulacion_tipo_documento")]
    operations = [
        migrations.AlterField(model_name="documentopostulacion", name="storage_key", field=models.CharField(db_index=True, max_length=500)),
        migrations.CreateModel(
            name="ClaveTemporalPostulacion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("rut", models.CharField(db_index=True, max_length=12)),
                ("email", models.EmailField(max_length=254)),
                ("codigo_hash", models.CharField(max_length=128)),
                ("expira_en", models.DateTimeField()),
                ("intentos", models.PositiveSmallIntegerField(default=0)),
                ("usada_en", models.DateTimeField(blank=True, null=True)),
                ("creada_en", models.DateTimeField(auto_now_add=True)),
            ], options={"ordering": ("-creada_en",)},
        ),
    ]
