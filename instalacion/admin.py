from django.contrib import admin
from .models import Instalacion, Zona

@admin.register(Instalacion)
class InstalacionAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre', 'comuna', 'nombre_contacto', 'correo_contacto', 'telefono_contacto', 'zona', 'estado_directiva')
    list_filter = ('zona', 'estado_directiva')
    search_fields = ('nombre', 'comuna', 'nombre_contacto')


@admin.register(Zona)
class ZonaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "codigo", "actualizado_en")
    search_fields = ("nombre", "codigo")
