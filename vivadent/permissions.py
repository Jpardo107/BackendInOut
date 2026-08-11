from rest_framework.permissions import BasePermission


class IsVivadentAdmin(BasePermission):
    message = "Este usuario no tiene acceso al administrador de Vivadent."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and hasattr(user, "vivadent_access")
            and user.vivadent_access.active
        )
