from django.contrib import admin
from .models import DocumentoItem, EstadoDocumentacion

@admin.register(DocumentoItem)
class DocumentoItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre')
    search_fields = ('nombre',)

@admin.register(EstadoDocumentacion)
class EstadoDocumentacionAdmin(admin.ModelAdmin):
    list_display = ('id', 'supervision', 'documento', 'cantidad_revisada', 'validez')
    list_filter = ('validez', 'documento')
    search_fields = ('documento__nombre',)
