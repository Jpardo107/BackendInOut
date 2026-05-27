from django.contrib import admin

from .models import ImagenReporteInforme, ReporteInforme


class ImagenReporteInformeInline(admin.TabularInline):
    model = ImagenReporteInforme
    extra = 0
    readonly_fields = ("storage_key", "nombre_original", "mime_type", "size", "creado_en")


@admin.register(ReporteInforme)
class ReporteInformeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "tipo_reporte",
        "instalacion",
        "usuario_creador",
        "estado",
        "criticidad_general",
        "fecha_emision",
        "creado_en",
    )
    list_filter = ("tipo_reporte", "estado", "criticidad_general", "instalacion", "fecha_emision")
    search_fields = ("autor_nombre", "instalacion__nombre", "descripcion_hechos")
    readonly_fields = ("creado_en", "actualizado_en")
    inlines = [ImagenReporteInformeInline]


@admin.register(ImagenReporteInforme)
class ImagenReporteInformeAdmin(admin.ModelAdmin):
    list_display = ("id", "reporte", "orden", "nombre_original", "mime_type", "size", "creado_en")
    list_filter = ("mime_type", "creado_en")
    search_fields = ("reporte__autor_nombre", "reporte__instalacion__nombre", "storage_key")
