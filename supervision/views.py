from rest_framework import viewsets, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from django.utils import timezone
from .models import Supervision, FotoSupervision
from .serializers import SupervisionSerializer, SupervisionDetailSerializer, FotoSupervisionSerializer


def get_mes_anio_from_request(request):
    now = timezone.localdate()
    mes = request.query_params.get("mes", now.month)
    anio = request.query_params.get("anio", now.year)

    try:
        mes = int(mes)
        anio = int(anio)
    except (TypeError, ValueError):
        raise ValidationError({"detail": "Los parametros mes y anio deben ser numericos."})

    if mes < 1 or mes > 12:
        raise ValidationError({"mes": "El mes debe estar entre 1 y 12."})

    if anio < 2000 or anio > now.year + 1:
        raise ValidationError({"anio": "El anio solicitado esta fuera del rango permitido."})

    return mes, anio


class SupervisionViewSet(viewsets.ModelViewSet):
    serializer_class = SupervisionSerializer

    def get_queryset(self):
        queryset = Supervision.objects.select_related('instalacion', 'supervisor').prefetch_related('fotos')

        if getattr(self, "action", None) == "list":
            mes, anio = get_mes_anio_from_request(self.request)
            queryset = queryset.filter(fecha__year=anio, fecha__month=mes)

        return queryset.order_by("-fecha", "-hora_inicio")

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
    serializer_class = SupervisionDetailSerializer

    def get_queryset(self):
        queryset = (
            Supervision.objects
            .select_related("instalacion", "supervisor")
            .prefetch_related(
                "estado_cargos_fijos",
                "estado_documentos",
                "fotos",
                "estado_cargos_fijos__cargo_fijo",
                "estado_documentos__documento",
            )
        )

        params_provided = "mes" in self.request.query_params or "anio" in self.request.query_params
        if getattr(self, "action", None) == "list" or params_provided:
            mes, anio = get_mes_anio_from_request(self.request)
            queryset = queryset.filter(fecha__year=anio, fecha__month=mes)

        return queryset.order_by("-fecha", "-hora_inicio")


class FotoSupervisionViewSet(viewsets.ModelViewSet):
    queryset = FotoSupervision.objects.all()
    serializer_class = FotoSupervisionSerializer
