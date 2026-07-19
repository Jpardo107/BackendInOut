from django.contrib import admin
from django import forms
from .models import Instalacion, Zona


class InstalacionAdminForm(forms.ModelForm):
    zona = forms.ChoiceField(label="Zona")

    class Meta:
        model = Instalacion
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = list(Zona.objects.order_by("nombre").values_list("codigo", "nombre"))
        zona_actual = getattr(self.instance, "zona", "") if self.instance else ""
        if zona_actual and zona_actual not in {codigo for codigo, _ in choices}:
            choices.append((zona_actual, f"{zona_actual} (zona antigua)"))
        self.fields["zona"].choices = choices

@admin.register(Instalacion)
class InstalacionAdmin(admin.ModelAdmin):
    form = InstalacionAdminForm
    list_display = ('id', 'nombre', 'comuna', 'nombre_contacto', 'correo_contacto', 'telefono_contacto', 'zona', 'estado_directiva')
    list_filter = ('zona', 'estado_directiva')
    search_fields = ('nombre', 'comuna', 'nombre_contacto')


@admin.register(Zona)
class ZonaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "codigo", "actualizado_en")
    search_fields = ("nombre", "codigo")
