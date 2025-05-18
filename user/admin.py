from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Usuario, Cargo

class UsuarioAdmin(UserAdmin):
    model = Usuario
    list_display = ('id', 'username', 'nombres', 'apellidos', 'rut', 'email', 'cargo', 'is_staff', 'is_active')
    list_filter = ('is_staff', 'is_active', 'cargo')
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Información personal', {'fields': ('nombres', 'apellidos', 'rut', 'email', 'cargo')}),
        ('Permisos', {'fields': ('is_staff', 'is_active', 'is_superuser', 'groups', 'user_permissions')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'nombres', 'apellidos', 'rut', 'email', 'cargo', 'password1', 'password2', 'is_staff', 'is_active')}
        ),
    )
    search_fields = ('username', 'rut', 'email')
    ordering = ('id',)

# Registrar los modelos
admin.site.register(Usuario, UsuarioAdmin)
admin.site.register(Cargo)