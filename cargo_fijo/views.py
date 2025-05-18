# cargo_fijo/views.py
from rest_framework import viewsets, generics
from .models import CargoFijoItem, EstadoCargoFijo
from .serializers import CargoFijoItemSerializer, EstadoCargoFijoSerializer
from rest_framework.response import Response

class CargoFijoItemViewSet(viewsets.ModelViewSet):
    queryset = CargoFijoItem.objects.all()
    serializer_class = CargoFijoItemSerializer

class EstadoCargoFijoViewSet(viewsets.ModelViewSet):
    queryset = EstadoCargoFijo.objects.all()
    serializer_class = EstadoCargoFijoSerializer

# NUEVA vista para creación masiva
class EstadoCargoFijoCreateAPIView(generics.CreateAPIView):
    queryset = EstadoCargoFijo.objects.all()
    serializer_class = EstadoCargoFijoSerializer

    def create(self, request, *args, **kwargs):
        many = isinstance(request.data, list)
        serializer = self.get_serializer(data=request.data, many=many)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data)
