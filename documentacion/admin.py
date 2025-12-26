from django.contrib import admin
from .models import DocumentoItem, EstadoDocumentacion, DocumentoInstalacion

@admin.register(DocumentoItem)
class DocumentoItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre')
    search_fields = ('nombre',)

@admin.register(EstadoDocumentacion)
class EstadoDocumentacionAdmin(admin.ModelAdmin):
    list_display = ('id', 'supervision', 'documento', 'cantidad_revisada', 'validez')
    list_filter = ('validez', 'documento')
    search_fields = ('documento__nombre',)

@admin.register(DocumentoInstalacion)
class DocumentoInstalacionAdmin(admin.ModelAdmin):
    list_display = ("id", "titulo", "instalacion", "categoria", "clasificacion", "created_at")
    list_filter = ("clasificacion", "categoria", "instalacion")
    search_fields = ("titulo", "nombre_original", "storage_key")