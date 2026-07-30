from django.contrib import admin

from .models import (
    DocumentoPostulacion,
    PostulacionGuardia,
    PreguntaPostulacion,
    TipoInstalacionLaboral,
    VacanteGuardia,
)


@admin.register(PostulacionGuardia)
class PostulacionGuardiaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre_completo", "rut", "estado", "estado_os10", "creado_en")
    list_filter = ("estado", "estado_os10", "comuna_residencia")
    search_fields = ("codigo", "rut", "nombres", "apellido_paterno", "email")
    readonly_fields = ("id_publico", "codigo", "acceso_hash", "creado_en", "actualizado_en")


admin.site.register(TipoInstalacionLaboral)
admin.site.register(VacanteGuardia)
admin.site.register(PreguntaPostulacion)
admin.site.register(DocumentoPostulacion)

