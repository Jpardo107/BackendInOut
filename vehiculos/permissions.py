from rest_framework.permissions import BasePermission


def can_manage_vehicles(user):
    cargo = str(getattr(getattr(user, "cargo", None), "nombre", "") or "").strip().lower()
    return bool(user and user.is_authenticated and user.is_active and (
        user.is_staff or user.is_superuser or any(
            role in cargo for role in ("admin", "coordinador de operaciones", "jefe de operaciones", "gerente", "controller", "rrhh")
        )
    ))


def can_use_vehicles(user):
    cargo = str(getattr(getattr(user, "cargo", None), "nombre", "") or "").strip().lower()
    return bool(user and user.is_authenticated and user.is_active and "supervisor" in cargo)


class VehiclePermission(BasePermission):
    message = "No tienes permisos para realizar esta operación de vehículos."

    def has_permission(self, request, view):
        if view.action == "movimiento":
            return can_use_vehicles(request.user)
        if view.action in {"list", "retrieve", "historial", "foto"}:
            return can_manage_vehicles(request.user) or can_use_vehicles(request.user)
        return can_manage_vehicles(request.user)
