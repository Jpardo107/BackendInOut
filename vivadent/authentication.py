from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication


class IsolatedJWTAuthentication(JWTAuthentication):
    """Impide que cuentas Vivadent consuman cualquier API interna de InOut."""

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None
        user, token = result
        is_vivadent = hasattr(user, "vivadent_access") and user.vivadent_access.active
        if is_vivadent and not request.path.startswith("/api/vivadent/"):
            raise AuthenticationFailed("Esta cuenta solo puede acceder a Vivadent.")
        return user, token
