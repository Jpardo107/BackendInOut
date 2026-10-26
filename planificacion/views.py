from datetime import timedelta

from rest_framework import status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from instalacion.models import Instalacion
from .models import Actividad, DiaEspecial, Pauta, TIPOS, JORNADAS
from .permissions import SoloJaime
from .serializers import ActividadSerializer, DiaSerializer, PautaSerializer, FiltroSerializer
from .services import actividades, calendario, resumen


class PersonalViewSet(viewsets.ModelViewSet):
    permission_classes = [SoloJaime]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return self.queryset.filter(usuario=self.request.user)

    def perform_create(self, serializer):
        serializer.save(usuario=self.request.user)


class PautaViewSet(PersonalViewSet):
    queryset = Pauta.objects.all()
    serializer_class = PautaSerializer
    http_method_names = ["get", "post", "head", "options"]

    def create(self, request, *args, **kwargs):
        # POST is an upsert for the selected effective date; earlier cycles stay intact.
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        instance, _ = Pauta.objects.update_or_create(usuario=request.user, inicio=data.pop("inicio"), defaults=data)
        return Response(self.get_serializer(instance).data, status=status.HTTP_200_OK)


class DiaViewSet(PersonalViewSet):
    queryset = DiaEspecial.objects.all()
    serializer_class = DiaSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        instance, _ = DiaEspecial.objects.update_or_create(usuario=request.user, fecha=data.pop("fecha"), defaults=data)
        return Response(self.get_serializer(instance).data, status=status.HTTP_200_OK)


class ActividadViewSet(PersonalViewSet):
    # Keep legacy request plans stored, but exclude this retired feature from the module.
    queryset = Actividad.objects.exclude(tipo="solicitud").exclude(registro_vinculado__startswith="solicitud:")
    serializer_class = ActividadSerializer

    def get_queryset(self):
        query = super().get_queryset()
        if self.action == "list":
            filters = FiltroSerializer(data=self.request.query_params)
            filters.is_valid(raise_exception=True)
            query = query.filter(fecha__range=(filters.validated_data["desde"], filters.validated_data["hasta"]))
        return query


@api_view(["GET"])
@permission_classes([SoloJaime])
def panel(request):
    serializer = FiltroSerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    f = serializer.validated_data
    rows = actividades(request.user, f)
    # Search beyond the displayed month, taking extras and future pauta changes into account.
    upcoming = calendario(request.user, f["desde"], f["desde"] + timedelta(days=366))
    next_free = next((d["fecha"] for d in upcoming if d["tipo"] == "libre"), None)
    return Response({
        "calendario": calendario(request.user, f["desde"], f["hasta"]),
        "proximo_libre": next_free,
        "actividades": rows,
        "resumen": resumen(request.user, f, rows),
    })


@api_view(["GET"])
@permission_classes([SoloJaime])
def opciones(request):
    return Response({
        "tipos": [{"value": k, "label": v} for k, v in TIPOS],
        "jornadas": [{"value": k, "label": v} for k, v in JORNADAS],
        "instalaciones": list(Instalacion.objects.order_by("nombre").values("id", "nombre")),
        "pautas": PautaSerializer(Pauta.objects.filter(usuario=request.user), many=True).data,
    })
