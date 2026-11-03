from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('vivadent', '0007_home_treatment_sections')]
    operations = [
        migrations.CreateModel(name='VisitNotification', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('session_id', models.CharField(max_length=64, unique=True)),
            ('path', models.CharField(max_length=300)),
            ('source', models.CharField(blank=True, max_length=100)),
            ('device', models.CharField(blank=True, max_length=20)),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('sent_at', models.DateTimeField(blank=True, null=True)),
            ('next_at', models.DateTimeField(db_index=True)),
            ('attempts', models.PositiveIntegerField(default=0)),
        ]),
        migrations.CreateModel(name='TelegramDispatch', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('next_send_at', models.DateTimeField()),
            ('lease', models.CharField(blank=True, max_length=36)),
        ]),
    ]
