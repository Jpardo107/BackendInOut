from django.contrib import admin

from .models import MovimientoInventario, PrendaInventario


@admin.register(PrendaInventario)
class PrendaInventarioAdmin(admin.ModelAdmin):
    list_display = (
        "nombre_prenda",
        "talla_prenda",
        "stock_actual",
        "stock_critico",
        "bajo_stock_critico",
        "codigo_barra",
        "activo",
    )
    list_filter = ("activo",)
    search_fields = ("nombre_prenda", "talla_prenda", "codigo_barra", "codigo_qr")
    readonly_fields = (
        "nombre_normalizado",
        "talla_normalizada",
        "codigo_barra",
        "codigo_qr",
        "creado_en",
        "actualizado_en",
    )


@admin.register(MovimientoInventario)
class MovimientoInventarioAdmin(admin.ModelAdmin):
    list_display = (
        "prenda",
        "tipo",
        "cantidad",
        "stock_antes",
        "stock_despues",
        "usuario_registro",
        "usuario_final",
        "creado_en",
    )
    list_filter = ("tipo", "creado_en")
    search_fields = (
        "prenda__nombre_prenda",
        "prenda__talla_prenda",
        "prenda__codigo_barra",
        "observacion",
    )
    readonly_fields = ("stock_antes", "stock_despues", "creado_en")
