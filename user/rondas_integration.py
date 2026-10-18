"""Private, exact lookup for RondApp; no personnel list is exposed."""
from django.conf import settings
from django.db.models import Value
from django.db.models.functions import Replace, Upper
from django.utils.crypto import constant_time_compare
from rest_framework import permissions, serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import PersonalEmpresa
from .services.rut import normalizar_rut


class RondAppServicePermission(permissions.BasePermission):
    def has_permission(self, request, view):
        expected = getattr(settings, "RONDAPP_INTEGRATION_KEY", "")
        supplied = request.headers.get("X-RondApp-Key", "")
        return bool(expected and supplied and constant_time_compare(expected, supplied))


class LookupSerializer(serializers.Serializer):
    rut = serializers.RegexField(r"^[0-9.kK-]{7,12}$", max_length=12)


class GuardiaRondasLookupView(APIView):
    authentication_classes = []
    permission_classes = [RondAppServicePermission]

    def post(self, request):
        serializer = LookupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rut = normalizar_rut(serializer.validated_data["rut"])
        people = PersonalEmpresa.objects.select_related("instalacion").annotate(
            rut_limpio=Upper(Replace(Replace("rut", Value("."), Value("")), Value("-"), Value("")))
        ).filter(rut_limpio=rut)
        # Reject duplicate legacy spellings rather than guessing a person's identity.
        if people.count() != 1:
            return Response({"detail": "No se encontró un guardia habilitado con ese RUT."}, status=404)
        person = people.first()
        if not person.activo:
            return Response({"detail": "El guardia no está activo en el listado de personal."}, status=403)
        if not person.instalacion_id:
            return Response({"detail": "El guardia no tiene una instalación asignada en InOut."}, status=409)
        response = Response({
            "id": person.id, "rut": person.rut, "nombre": person.nombre_completo,
            "instalacion": {"id": person.instalacion_id, "nombre": person.instalacion.nombre},
        })
        response["Cache-Control"] = "no-store"
        return response
