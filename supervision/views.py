from rest_framework import viewsets, status
from rest_framework.response import Response
from .models import Supervision, FotoSupervision
from .serializers import SupervisionSerializer, SupervisionDetailSerializer, FotoSupervisionSerializer


class SupervisionViewSet(viewsets.ModelViewSet):
    serializer_class = SupervisionSerializer

    def get_queryset(self):
        return Supervision.objects.select_related('instalacion', 'supervisor').prefetch_related('fotos')

    def partial_update(self, request, *args, **kwargs):
        """Sobrescribimos PATCH para restringirlo solo a 'estado_solicitud'."""
        # Obtenemos la instancia actual
        instance = self.get_object()
        data = request.data

        # Validamos que solo 'estado_solicitud' esté presente en la solicitud
        if set(data.keys()) != {'estado_solicitud'}:
            return Response(
                {"error": "Solo puedes actualizar el campo 'estado_solicitud'."},
                status=status.HTTP_400_BAD_REQUEST
            )
        # Validamos que el 'estado_solicitud' tenga un valor permitido
        allowed_states = ['gestionado', 'entregado', 'denegado', 'pendiente']
        if data['estado_solicitud'] not in allowed_states:
            return Response(
                {"estado_solicitud": f"Estado no válido. Los valores permitidos son: {', '.join(allowed_states)}."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Actualizamos únicamente el campo 'estado_solicitud'
        instance.estado_solicitud = data['estado_solicitud']
        instance.save()

        # Retornamos la instancia actualizada
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class SupervisionDetailViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Supervision.objects.select_related('instalacion', 'supervisor') \
        .prefetch_related('estado_cargos_fijos', 'estado_documentos', 'fotos')
    serializer_class = SupervisionDetailSerializer


class FotoSupervisionViewSet(viewsets.ModelViewSet):
    queryset = FotoSupervision.objects.all()
    serializer_class = FotoSupervisionSerializer
