from django.contrib import admin
from .models import CargoFijoItem, EstadoCargoFijo

@admin.register(CargoFijoItem)
class CargoFijoItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre')
    search_fields = ('nombre',)

@admin.register(EstadoCargoFijo)
class EstadoCargoFijoAdmin(admin.ModelAdmin):
    list_display = ('id', 'supervision', 'cargo_fijo')
    list_filter = ('cargo_fijo',)