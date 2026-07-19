from django.db import migrations, models


def crear_zonas_iniciales(apps, schema_editor):
    Zona = apps.get_model("instalacion", "Zona")
    Instalacion = apps.get_model("instalacion", "Instalacion")
    nombres = {"norte": "Norte", "centro": "Centro", "sur": "Sur", "tw": "TW"}
    codigos = set(Instalacion.objects.exclude(zona="").values_list("zona", flat=True))
    codigos.update(nombres)
    for codigo in codigos:
        Zona.objects.get_or_create(codigo=codigo, defaults={"nombre": nombres.get(codigo, codigo.replace("-", " ").title())})


class Migration(migrations.Migration):
    dependencies = [("instalacion", "0004_instalacion_estado_directiva")]
    operations = [
        migrations.CreateModel(
            name="Zona",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("codigo", models.SlugField(max_length=50, unique=True)),
                ("nombre", models.CharField(max_length=100, unique=True)),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("actualizado_en", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ("nombre", "id")},
        ),
        migrations.AlterField(
            model_name="instalacion",
            name="zona",
            field=models.CharField(db_index=True, default="centro", max_length=50),
        ),
        migrations.RunPython(crear_zonas_iniciales, migrations.RunPython.noop),
    ]
