from django.db import migrations


def rename_featured(apps, schema_editor):
    Collection = apps.get_model('vivadent', 'StoreCollection')
    Collection.objects.filter(key='tienda', title='Tu mejor sonrisa empieza aquí').update(
        title='Popular en estos momentos',
    )


class Migration(migrations.Migration):
    dependencies = [('vivadent', '0005_refresh_store_collections')]
    operations = [migrations.RunPython(rename_featured, migrations.RunPython.noop)]
