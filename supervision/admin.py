from django.contrib import admin
from .models import Supervision
from cargo_fijo.models import EstadoCargoFijo
from documentacion.models import EstadoDocumentacion

class EstadoCargoFijoInline(admin.TabularInline):
    model = EstadoCargoFijo
    extra = 1

class EstadoDocumentacionInline(admin.TabularInline):
    model = EstadoDocumentacion
    extra = 1



@admin.register(Supervision)
class SupervisionAdmin(admin.ModelAdmin):
    list_display = ('id', 'instalacion', 'supervisor', 'fecha', 'hora_inicio', 'hora_final')
    list_filter = ('fecha', 'instalacion', 'supervisor')
    search_fields = ('instalacion__nombre', 'supervisor__username')
    inlines = [EstadoCargoFijoInline, EstadoDocumentacionInline]
