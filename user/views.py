from rest_framework import generics, permissions
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import Usuario
from .serializers import CustomTokenObtainPairSerializer, SupervisorSerializer


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

class SupervisorListView(generics.ListAPIView):
    serializer_class = SupervisorSerializer
    permission_classes = [permissions.IsAuthenticated]  # Puedes cambiar a AllowAny si quieres público

    def get_queryset(self):
        return Usuario.objects.filter(cargo__nombre__iexact='Supervisor')