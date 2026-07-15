from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("inventario", "0006_configuracionalertastock_registroalertastock")]

    operations = [
        migrations.RemoveConstraint(
            model_name="prendainventario",
            name="unique_prenda_talla_normalizada",
        ),
        migrations.AddField(
            model_name="prendainventario",
            name="categoria",
            field=models.CharField(
                choices=[
                    ("vestuario_equipo", "Vestuario y equipo"),
                    ("cargo_fijo", "Cargo fijo"),
                ],
                db_index=True,
                default="vestuario_equipo",
                max_length=30,
            ),
        ),
        migrations.RemoveIndex(
            model_name="prendainventario",
            name="inventario__nombre__00d853_idx",
        ),
        migrations.AddConstraint(
            model_name="prendainventario",
            constraint=models.UniqueConstraint(
                fields=("categoria", "nombre_normalizado", "talla_normalizada"),
                name="unique_categoria_prenda_talla_normalizada",
            ),
        ),
        migrations.AddIndex(
            model_name="prendainventario",
            index=models.Index(
                fields=["categoria", "nombre_normalizado", "talla_normalizada"],
                name="inventario_categori_30ca1b_idx",
            ),
        ),
    ]
