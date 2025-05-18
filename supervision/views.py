from rest_framework import viewsets
from .models import Supervision, FotoSupervision
from .serializers import SupervisionSerializer, SupervisionDetailSerializer, FotoSupervisionSerializer


class SupervisionViewSet(viewsets.ModelViewSet):
    serializer_class = SupervisionSerializer

    def get_queryset(self):
        return Supervision.objects.select_related('instalacion', 'supervisor').prefetch_related('fotos')


class SupervisionDetailViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Supervision.objects.select_related('instalacion', 'supervisor') \
        .prefetch_related('estado_cargos_fijos', 'estado_documentos', 'fotos')
    serializer_class = SupervisionDetailSerializer


class FotoSupervisionViewSet(viewsets.ModelViewSet):
    queryset = FotoSupervision.objects.all()
    serializer_class = FotoSupervisionSerializer