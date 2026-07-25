from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inventario", "0007_prendainventario_categoria"),
    ]

    operations = [
        migrations.AlterField(
            model_name="prendainventario",
            name="categoria",
            field=models.CharField(
                choices=[
                    ("vestuario_equipo", "Vestuario y equipo"),
                    ("cargo_fijo", "Cargo fijo"),
                    ("utiles_aseo", "Útiles de aseo"),
                ],
                db_index=True,
                default="vestuario_equipo",
                max_length=30,
            ),
        ),
    ]
