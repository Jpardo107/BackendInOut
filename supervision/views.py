from rest_framework import viewsets, status
from rest_framework.response import Response
from .models import Supervision, FotoSupervision
from .serializers import SupervisionSerializer, SupervisionDetailSerializer, FotoSupervisionSerializer


class SupervisionViewSet(viewsets.ModelViewSet):
    serializer_class = SupervisionSerializer

    def get_queryset(self):
        return Supervision.objects.select_related('instalacion', 'supervisor').prefetch_related('fotos')

    def update(self, request, *args, **kwargs):
        """Sobrescribimos update para controlar solo la edición de estado_solicitud."""
        partial = kwargs.pop('partial', False)  # Si es un PATCH, partial será True
        instance = self.get_object()  # Obtenemos la instancia actual de la supervisión
        data = request.data

        # Validar si el usuario intenta modificar únicamente 'estado_solicitud'
        if 'estado_solicitud' not in data:
            return Response(
                {"error": "Solo se permite editar el campo 'estado_solicitud'."},
                status=status.HTTP_400_BAD_REQUEST
            )
            # Verificar que el valor proporcionado para 'estado_solicitud' sea válido
            allowed_states = ['gestionado', 'entregado', 'denegado']
            if data['estado_solicitud'] not in allowed_states:
                return Response(
                    {
                        "estado_solicitud": f"El estado no es válido. Los valores permitidos son: {', '.join(allowed_states)}."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Actualizar únicamente 'estado_solicitud'
            instance.estado_solicitud = data['estado_solicitud']
            instance.save()

            # Devolver la instancia actualizada como respuesta
            serializer = self.get_serializer(instance)
            return Response(serializer.data)


class SupervisionDetailViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Supervision.objects.select_related('instalacion', 'supervisor') \
        .prefetch_related('estado_cargos_fijos', 'estado_documentos', 'fotos')
    serializer_class = SupervisionDetailSerializer


class FotoSupervisionViewSet(viewsets.ModelViewSet):
    queryset = FotoSupervision.objects.all()
    serializer_class = FotoSupervisionSerializer