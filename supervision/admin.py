from django.contrib import admin
from .models import Supervision, SupervisionActiva, RendicionGasto
from cargo_fijo.models import EstadoCargoFijo
from documentacion.models import EstadoDocumentacion


@admin.register(RendicionGasto)
class RendicionGastoAdmin(admin.ModelAdmin):
    list_display = ("id", "supervisor_nombre", "instalacion", "persona", "monto", "motivo", "creada_en")
    list_filter = ("creada_en", "supervisor")
    search_fields = ("supervisor_nombre", "instalacion", "persona", "motivo")
    readonly_fields = ("supervisor", "supervisor_nombre", "instalacion", "persona", "monto", "motivo", "creada_en", "storage_key")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

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


@admin.register(SupervisionActiva)
class SupervisionActivaAdmin(admin.ModelAdmin):
    list_display = ("supervisor", "instalacion", "fecha", "hora_inicio", "actualizada_en")
    list_filter = ("fecha", "instalacion")
