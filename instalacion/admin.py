from django.contrib import admin
from .models import Instalacion

@admin.register(Instalacion)
class InstalacionAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre', 'comuna', 'nombre_contacto', 'correo_contacto', 'telefono_contacto', 'zona')
    search_fields = ('nombre', 'comuna', 'nombre_contacto')
