# instalacion/views.py

from rest_framework import viewsets, permissions
from rest_framework.exceptions import ValidationError
from .models import Instalacion, Zona
from .serializers import InstalacionSerializer, ZonaSerializer


class IsZonaAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        cargo = str(getattr(getattr(request.user, "cargo", None), "nombre", "") or "").lower()
        return bool(request.user and request.user.is_authenticated and (
            request.user.is_staff or request.user.is_superuser
            or any(role in cargo for role in ("admin", "administrativo", "rrhh"))
        ))


class ZonaViewSet(viewsets.ModelViewSet):
    queryset = Zona.objects.all()
    serializer_class = ZonaSerializer
    permission_classes = [IsZonaAdmin]

    def perform_destroy(self, instance):
        cantidad = Instalacion.objects.filter(zona=instance.codigo).count()
        if cantidad:
            raise ValidationError({"detail": f"No se puede eliminar la zona porque tiene {cantidad} instalación(es) asignada(s)."})
        instance.delete()

class InstalacionViewSet(viewsets.ModelViewSet):
    queryset = Instalacion.objects.all()
    serializer_class = InstalacionSerializer
    permission_classes = [permissions.IsAuthenticated]  # Solo usuarios autenticados
