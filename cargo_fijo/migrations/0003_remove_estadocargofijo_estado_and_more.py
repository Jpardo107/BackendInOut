# Generated by Django 5.2 on 2025-04-26 03:39

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cargo_fijo', '0002_estadocargofijo'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='estadocargofijo',
            name='estado',
        ),
        migrations.AddField(
            model_name='estadocargofijo',
            name='cantidad_revisada',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
