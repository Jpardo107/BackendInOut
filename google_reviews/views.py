from django.core.exceptions import ImproperlyConfigured
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import GooglePlacesError, get_google_reviews


class GoogleReviewsView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            return Response(get_google_reviews())
        except ImproperlyConfigured as error:
            return Response({"detail": str(error)}, status=503)
        except GooglePlacesError:
            # No se filtran al cliente detalles de la cuenta o clave de Google.
            return Response(
                {"detail": "Las reseñas no están disponibles temporalmente."},
                status=502,
            )
