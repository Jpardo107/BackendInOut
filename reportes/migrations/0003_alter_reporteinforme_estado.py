from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("reportes", "0002_reporteinforme_archivo_origen_mime_type_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="reporteinforme",
            name="estado",
            field=models.CharField(
                choices=[
                    ("borrador", "Borrador"),
                    ("procesando_ia", "Procesando IA"),
                    ("generado", "Generado"),
                    ("error_ia", "Error IA"),
                ],
                default="borrador",
                max_length=20,
            ),
        ),
    ]
