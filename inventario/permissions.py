from rest_framework.permissions import BasePermission


class IsInventarioRole(BasePermission):
    message = "No tienes permisos para acceder al modulo de inventario."

    def has_permission(self, request, view):
        user = request.user
        cargo = getattr(getattr(user, "cargo", None), "nombre", "") or ""
        cargo = cargo.strip().lower()
        return bool(user and user.is_authenticated and ("rrhh" in cargo or "supervisor" in cargo))
