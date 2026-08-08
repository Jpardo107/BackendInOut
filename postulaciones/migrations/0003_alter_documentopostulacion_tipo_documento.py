from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("postulaciones", "0002_catalogos_iniciales"),
    ]

    operations = [
        migrations.AlterField(
            model_name="documentopostulacion",
            name="tipo_documento",
            field=models.CharField(
                choices=[
                    ("cedula_frontal", "Cédula frontal"),
                    ("cedula_posterior", "Cédula posterior"),
                    ("certificado_os10", "Certificado OS10"),
                    ("curriculum", "Currículum"),
                    ("certificado_estudios", "Certificado de estudios"),
                    ("licencia_conducir", "Licencia de conducir"),
                    ("documentacion_migratoria", "Documentación migratoria"),
                    ("otro", "Otro antecedente"),
                ],
                max_length=60,
            ),
        ),
    ]
