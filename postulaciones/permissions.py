from rest_framework.permissions import BasePermission


class IsPostulacionesAdmin(BasePermission):
    message = "No tienes permisos para gestionar postulaciones."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        cargo = (getattr(getattr(request.user, "cargo", None), "nombre", "") or "").lower()
        return request.user.is_staff or request.user.is_superuser or any(
            role in cargo for role in ("rrhh", "recursos humanos", "reclut", "administrador")
        )

