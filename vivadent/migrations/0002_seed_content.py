from django.db import migrations


PROMOTIONS = [
    ("Limpieza dental completa", "Una sonrisa fresca y saludable", "$29.990", "Higiene profesional para remover placa y sarro, cuidar tus encías y prevenir problemas bucales."),
    ("Blanqueamiento dental", "Realza el brillo de tu sonrisa", "$89.990", "Tratamiento supervisado para aclarar el tono de tus dientes de forma controlada y lograr un resultado natural."),
    ("Radiografía panorámica", "Diagnóstico preciso y oportuno", "$18.000", "Obtén una vista completa de dientes y maxilares, realizada directamente en nuestra clínica con entrega digital."),
    ("Armonización facial", "Equilibrio que respeta tu esencia", "Desde $169.990", "Evaluación personalizada para realzar tus rasgos con resultados naturales."),
]

TEXTS = {
    "inicio": {"eyebrow": "Tu sonrisa comienza aquí", "title": "La sonrisa que quieres, con el cuidado que mereces.", "description": "Odontología cercana, moderna y pensada para ti. Te acompañamos con tratamientos personalizados y un equipo que escucha de verdad.", "button": "Agenda tu evaluación"},
    "servicios": {"eyebrow": "Nuestros servicios", "title": "Cuidado dental, estética y radiografías en un solo lugar", "description": "Todo lo que necesitas para cuidar tu sonrisa y realzar tu rostro, con atención cercana y tecnología moderna."},
    "promociones": {"eyebrow": "Promociones Vivadent", "title": "Una buena razón para empezar a cuidarte hoy", "description": "Beneficios pensados para acercarte al tratamiento que necesitas."},
    "nosotros": {"eyebrow": "¿Por qué Vivadent?", "title": "Queremos que venir al dentista se sienta diferente", "description": "Con más de 18 años de servicio, creemos en una odontología honesta y humana."},
}


def seed(apps, schema_editor):
    Promotion = apps.get_model("vivadent", "Promotion")
    SiteText = apps.get_model("vivadent", "SiteText")
    for order, values in enumerate(PROMOTIONS):
        Promotion.objects.get_or_create(title=values[0], defaults={"subtitle": values[1], "price": values[2], "description": values[3], "order": order, "status": "active"})
    for section, fields in TEXTS.items():
        for key, value in fields.items():
            SiteText.objects.get_or_create(section=section, key=key, defaults={"value": value})


class Migration(migrations.Migration):
    dependencies = [("vivadent", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
