from django.db import models
from django.db.models import Count
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import PersonalEmpresa, Usuario
from .serializers import (
    CustomTokenObtainPairSerializer,
    PersonalEmpresaSerializer,
    SupervisorSerializer,
)
from .services.personal_excel import parse_personal_excel
from .services.instalacion_matcher import construir_indice_instalaciones, buscar_instalacion


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

class SupervisorListView(generics.ListAPIView):
    serializer_class = SupervisorSerializer
    permission_classes = [permissions.IsAuthenticated]  # Puedes cambiar a AllowAny si quieres público

    def get_queryset(self):
        return (
            Usuario.objects.filter(
                models.Q(cargo__nombre__iexact="Supervisor")
                | models.Q(cargo__nombre__iexact="Coordinador de Operaciones")
            )
            .select_related("cargo")
            .order_by("nombres", "apellidos")
        )


class PersonalEmpresaViewSet(viewsets.ModelViewSet):
    serializer_class = PersonalEmpresaSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def get_queryset(self):
        queryset = PersonalEmpresa.objects.select_related("instalacion")
        search = self.request.query_params.get("search", "").strip()
        ubicacion = self.request.query_params.get("ubicacion", "").strip()
        activo = self.request.query_params.get("activo")
        limit = self.request.query_params.get("limit")

        if search:
            queryset = queryset.filter(
                models.Q(nombre_completo__icontains=search)
                | models.Q(rut__icontains=search.replace(".", "").replace("-", ""))
            )

        if ubicacion:
            queryset = queryset.filter(ubicacion__iexact=ubicacion)

        if activo is not None:
            queryset = queryset.filter(activo=activo.lower() in ("1", "true", "si", "yes"))

        queryset = queryset.order_by("nombre_completo")

        if limit:
            try:
                limit = min(max(int(limit), 1), 50)
                queryset = queryset[:limit]
            except (TypeError, ValueError):
                pass

        return queryset

    @action(detail=False, methods=["get"], url_path="dashboard")
    def dashboard(self, request):
        total = PersonalEmpresa.objects.count()
        activos = PersonalEmpresa.objects.filter(activo=True).count()
        inactivos = total - activos
        por_ubicacion = (
            PersonalEmpresa.objects
            .values("ubicacion")
            .annotate(total=Count("id"))
            .order_by("-total", "ubicacion")
        )

        return Response({
            "total": total,
            "activos": activos,
            "inactivos": inactivos,
            "ubicaciones": [
                {"ubicacion": item["ubicacion"] or "SIN UBICACION", "total": item["total"]}
                for item in por_ubicacion
            ],
        })

    @action(detail=False, methods=["post"], url_path="carga-masiva")
    def carga_masiva(self, request):
        archivo = request.FILES.get("archivo")
        if not archivo:
            return Response(
                {"archivo": "Debes adjuntar un archivo Excel."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        personal_rows, errores = parse_personal_excel(archivo)
        creados = 0
        actualizados = 0
        vinculados = 0
        indice_instalaciones = construir_indice_instalaciones()

        for row in personal_rows:
            instalacion = buscar_instalacion(row["ubicacion"], indice_instalaciones)
            defaults = {
                "nombre_completo": row["nombre_completo"],
                "ubicacion": row["ubicacion"],
                "activo": True,
            }
            # No borra una relación existente si el texto del Excel no coincide.
            if instalacion:
                defaults["instalacion"] = instalacion
                vinculados += 1

            _, created = PersonalEmpresa.objects.update_or_create(
                rut=row["rut"],
                defaults=defaults,
            )
            if created:
                creados += 1
            else:
                actualizados += 1

        return Response({
            "procesados": len(personal_rows),
            "creados": creados,
            "actualizados": actualizados,
            "vinculados": vinculados,
            "omitidos": len(errores),
            "errores": errores[:30],
        })
