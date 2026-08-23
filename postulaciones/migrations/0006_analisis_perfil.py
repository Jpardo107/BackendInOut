from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("postulaciones", "0005_postulacion_sin_antecedentes")]
    operations = [
        migrations.AddField(model_name="postulacionguardia", name="score_perfil", field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name="postulacionguardia", name="resumen_ia", field=models.TextField(blank=True)),
        migrations.AddField(model_name="postulacionguardia", name="analizado_en", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="postulacionguardia", name="vacante_recomendada", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="postulantes_recomendados", to="postulaciones.vacanteguardia")),
    ]
