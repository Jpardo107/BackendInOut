import unicodedata
from django.db import migrations


def seed(apps, schema_editor):
    Promotion = apps.get_model('vivadent', 'Promotion')
    Collection = apps.get_model('vivadent', 'StoreCollection')
    promotions = list(Promotion.objects.filter(status='active').order_by('order', 'id'))
    def words(p):
        return ''.join(c for c in unicodedata.normalize('NFD', p.title.lower()) if unicodedata.category(c) != 'Mn')
    definitions = [
        ('tienda', 'Destacados para cuidarte', 'SELECCIÓN VIVADENT', 'Una selección de nuestra tienda para dar el primer paso.', [p.id for p in promotions[:4]]),
        ('packs', 'Descubre nuestros packs', 'MÁS EN UNA SOLA ELECCIÓN', 'Revisa lo que incluye cada pack y encuentra una opción para ti.', [p.id for p in promotions if any(x in words(p) for x in ['pack', '+', 'rinolips'])]),
        ('facial', 'Tu espacio de armonización facial', 'UN CUIDADO MUY TUYO', 'Conoce las opciones y resuelve tus dudas con nuestro equipo.', [p.id for p in promotions if any(x in words(p) for x in ['facial', 'botox', 'labios', 'rino', 'hialuronico'])]),
    ]
    for order, (key, title, eyebrow, description, ids) in enumerate(definitions):
        Collection.objects.get_or_create(key=key, defaults=dict(title=title, eyebrow=eyebrow, description=description, order=order, promotion_ids=ids))


class Migration(migrations.Migration):
    dependencies = [('vivadent', '0003_storecollection_storesession_analyticsevent_event_id_and_more')]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
