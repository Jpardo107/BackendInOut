"""Retire the packs section without deleting its treatments or saved selection."""
from django.db import migrations


def refresh(apps, schema_editor):
    Collection = apps.get_model('vivadent', 'StoreCollection')
    Collection.objects.filter(key='packs').update(enabled=False)
    Collection.objects.filter(key='tienda', title__in=['Destacados para cuidarte', 'Los más pedidos']).update(
        title='Tu mejor sonrisa empieza aquí',
        eyebrow='ELIGE HOY. EMPIEZA POR TI.',
        description='Ese cuidado que tienes en mente está a un clic. Encuentra tu tratamiento, agrégalo al carrito y compra online.',
    )
    Collection.objects.filter(key='facial', title='Tu espacio de armonización facial').update(
        title='Armonización facial, a tu medida',
        eyebrow='ESTÉTICA FACIAL VIVADENT',
        description='Labios, perfil y cuidado facial. Explora nuestras opciones y encuentra el tratamiento que quieres consultar con nuestro equipo.',
    )
    Collection.objects.filter(key='tienda').update(order=0)
    Collection.objects.filter(key='facial').update(order=1)


class Migration(migrations.Migration):
    dependencies = [('vivadent', '0004_seed_store_collections')]
    operations = [migrations.RunPython(refresh, migrations.RunPython.noop)]
