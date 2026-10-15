"""Organize the storefront without deleting promotions or existing selections."""
import re
import unicodedata
from django.db import migrations


def organize(apps, schema_editor):
    Promotion = apps.get_model('vivadent', 'Promotion')
    Collection = apps.get_model('vivadent', 'StoreCollection')
    groups = {'dental': [], 'facial': [], 'radiologia': []}
    featured = []
    for p in Promotion.objects.all().order_by('order', 'id'):
        title = ''.join(c for c in unicodedata.normalize('NFD', p.title.lower()) if unicodedata.category(c) != 'Mn')
        if re.search(r'radiogra|radiolo|bite[ -]?wing|periapical|scanner|panoramica|telerradio|teleradio|ortopantom|cone[ -]?beam|cbct|tomogra|cefalometr', title):
            key = 'radiologia'
        elif re.search(r'botox|labio|rino|armoniza|facial|hialuron|bioestimula|salmon', title):
            key = 'facial'
        else:
            key = 'dental'
        groups[key].append(p.id)
        if re.search(r'pack|ortodon|bracket|promo|\+', title):
            featured.append(p.id)
    definitions = [
        ('tienda', 'Destacados', 'PROMOCIONES Y PACKS', 'Promociones, ortodoncia y packs para dar el próximo paso.', featured),
        ('dental', 'Salud Dental', 'CUIDA TU SONRISA', 'Prevención, estética y tratamientos para cuidar tu sonrisa.', groups['dental']),
        ('facial', 'Armonización Facial', 'UN CUIDADO PARA TI', 'Conoce nuestras opciones para el cuidado y la armonía de tus rasgos.', groups['facial']),
        ('radiologia', 'Radiografías', 'DIAGNÓSTICO EN LA CLÍNICA', 'Encuentra el examen que indicó tu profesional.', groups['radiologia']),
    ]
    for order, (key, title, eyebrow, description, ids) in enumerate(definitions):
        collection, created = Collection.objects.get_or_create(key=key, defaults=dict(title=title, eyebrow=eyebrow, description=description, promotion_ids=ids, order=order))
        if not created:
            collection.title = title
            collection.order = order
            # Retain saved picks and bring existing packs into Destacados.
            if key == 'tienda':
                packs = Collection.objects.filter(key='packs').first()
                collection.promotion_ids = list(dict.fromkeys(collection.promotion_ids + ids + (packs.promotion_ids if packs else [])))
            elif key == 'facial':
                collection.promotion_ids = list(dict.fromkeys(collection.promotion_ids + ids))
            collection.save(update_fields=['title', 'order', 'promotion_ids'])
    Collection.objects.filter(key='packs').update(enabled=False)


class Migration(migrations.Migration):
    dependencies = [('vivadent', '0006_rename_featured_collection')]
    operations = [migrations.RunPython(organize, migrations.RunPython.noop)]
