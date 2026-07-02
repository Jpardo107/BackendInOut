from rest_framework.permissions import BasePermission


class IsInventarioRole(BasePermission):
    message = "No tienes permisos para acceder al modulo de inventario."

    def has_permission(self, request, view):
        user = request.user
        cargo = getattr(getattr(user, "cargo", None), "nombre", "") or ""
        cargo = cargo.strip().lower()
        allowed_cargo = any(
            role in cargo
            for role in ("rrhh", "supervisor", "administrador", "administrativo", "admin")
        )
        return bool(
            user
            and user.is_authenticated
            and (user.is_staff or user.is_superuser or allowed_cargo)
        )
