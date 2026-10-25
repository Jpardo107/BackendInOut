from rest_framework.permissions import BasePermission


def es_jaime(user):
    # Only punctuation used in a formatted RUT is ignored; never trust a name/role.
    rut = str(getattr(user, "rut", "") or "").replace(".", "").replace("-", "").replace(" ", "").upper()
    return bool(user and user.is_authenticated and user.is_active and rut == "175119426")


class SoloJaime(BasePermission):
    message = "Este módulo es de uso personal de Jaime Pardo."

    def has_permission(self, request, view):
        return es_jaime(request.user)
