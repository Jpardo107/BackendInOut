import json
import logging
from uuid import uuid4

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from documentacion.services.r2_storage import delete_document, generate_signed_url, upload_document
from .models import FotoVehiculo, MovimientoVehiculo, Vehiculo
from .permissions import VehiclePermission, can_manage_vehicles, can_use_vehicles
from .serializers import MovimientoEntradaSerializer, MovimientoSerializer, VehiculoSerializer

logger = logging.getLogger(__name__)


class Conflict(APIException):
    status_code = 409
    default_detail = "El vehículo cambió de estado. Actualiza la lista e intenta nuevamente."


class HistoryPagination(PageNumberPagination):
    page_size = 10


class VehiculoViewSet(viewsets.ModelViewSet):
    serializer_class = VehiculoSerializer
    permission_classes = [VehiclePermission]
    pagination_class = None

    def get_queryset(self):
        qs = Vehiculo.objects.select_related("supervisor_actual")
        if not can_manage_vehicles(self.request.user):
            qs = qs.filter(Q(activo=True) | Q(supervisor_actual=self.request.user))
        return qs

    def list(self, request, *args, **kwargs):
        return Response({
            "results": self.get_serializer(self.get_queryset(), many=True).data,
            "puede_administrar": can_manage_vehicles(request.user),
            "puede_operar": can_use_vehicles(request.user),
        })

    def perform_create(self, serializer):
        try:
            with transaction.atomic():
                serializer.save()
        except IntegrityError as exc:
            raise ValidationError("Esta patente ya está registrada.") from exc

    def update(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                obj = get_object_or_404(self.get_queryset().select_related(None).select_for_update(), pk=kwargs["pk"])
                serializer = self.get_serializer(obj, data=request.data, partial=kwargs.get("partial", False))
                serializer.is_valid(raise_exception=True)
                if not Vehiculo.objects.filter(pk=obj.pk, version=obj.version).update(
                    **serializer.validated_data, version=F("version") + 1
                ):
                    raise Conflict()
                obj.refresh_from_db()
                return Response(self.get_serializer(obj).data)
        except IntegrityError as exc:
            raise ValidationError("Esta patente ya está registrada.") from exc

    def destroy(self, request, *args, **kwargs):
        with transaction.atomic():
            obj = get_object_or_404(self.get_queryset().select_related(None).select_for_update(), pk=kwargs["pk"])
            if obj.supervisor_actual_id:
                raise Conflict("El supervisor debe completar la entrega antes de eliminar el vehículo.")
            if obj.movimientos.exists():
                raise ValidationError("Este vehículo tiene historial. Desactívalo para conservar sus registros.")
            obj.delete()
        return Response(status=204)

    def history_queryset(self, vehicle):
        qs = vehicle.movimientos.prefetch_related("fotos")
        if not can_manage_vehicles(self.request.user):
            qs = qs.filter(supervisor=self.request.user)
        return qs

    @action(detail=True, methods=["get"])
    def historial(self, request, pk=None):
        paginator = HistoryPagination()
        page = paginator.paginate_queryset(self.history_queryset(self.get_object()), request)
        return paginator.get_paginated_response(MovimientoSerializer(page, many=True).data)

    @action(detail=True, methods=["get"])
    def foto(self, request, pk=None):
        foto_id = serializers.IntegerField(min_value=1).run_validation(request.query_params.get("foto"))
        photo = get_object_or_404(FotoVehiculo, pk=foto_id,
                                movimiento__in=self.history_queryset(self.get_object()))
        try:
            url = generate_signed_url(photo.storage_key, expires=3600)
        except Exception as exc:
            logger.exception("No se pudo abrir la foto del vehículo")
            raise APIException("No se pudo abrir la foto. Intenta nuevamente.") from exc
        return Response({"url": url})

    def existing_movement(self, vehicle, data):
        existing = MovimientoVehiculo.objects.filter(solicitud_id=data["solicitud_id"]).first()
        if existing and (existing.vehiculo_id != vehicle.pk or existing.supervisor_id != self.request.user.pk
                         or existing.tipo != data["tipo"]):
            raise Conflict("La solicitud ya fue utilizada en otro registro.")
        return existing

    def validate_state(self, vehicle, data):
        if vehicle.version != data["version"]:
            raise Conflict()
        if data["tipo"] == "recepcion":
            if not vehicle.activo:
                raise Conflict("El vehículo está desactivado.")
            if vehicle.supervisor_actual_id:
                raise Conflict("El vehículo está en uso. Su supervisor debe completar la entrega.")
        elif vehicle.supervisor_actual_id != self.request.user.pk:
            raise Conflict("Solo el supervisor que recibió el vehículo puede entregarlo.")
        if data["kilometraje"] < vehicle.kilometraje_actual:
            raise ValidationError({"kilometraje": f"No puede ser menor a {vehicle.kilometraje_actual} km."})

    @action(detail=True, methods=["post"])
    def movimiento(self, request, pk=None):
        vehicle = self.get_object()
        try:
            payload = json.loads(request.data.get("datos", "{}"))
        except (ValueError, TypeError) as exc:
            raise ValidationError("Los datos del registro no son válidos.") from exc
        serializer = MovimientoEntradaSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        existing = self.existing_movement(vehicle, data)
        if existing:
            return Response(MovimientoSerializer(existing).data)
        self.validate_state(vehicle, data)

        # Validate every image before uploading anything or changing custody.
        metadata = data["fotos"]
        expected = {f"foto_{index}" for index in range(len(metadata))}
        if set(request.FILES) != expected or any(len(request.FILES.getlist(key)) != 1 for key in expected):
            raise ValidationError("Adjunta todas las fotografías del registro.")
        files = []
        for index in range(len(metadata)):
            file = request.FILES[f"foto_{index}"]
            if file.size > 10 * 1024 * 1024:
                raise ValidationError(f"La fotografía {index + 1} supera los 10 MB.")
            try:
                image = serializers.ImageField().run_validation(file)
            except DjangoValidationError as exc:
                raise ValidationError(f"La fotografía {index + 1} no es una imagen válida.") from exc
            if image.image.format not in {"JPEG", "PNG", "WEBP"}:
                raise ValidationError("Las fotografías deben ser JPG, PNG o WebP.")
            files.append(image)

        uploaded = []
        committed = False
        try:
            for file in files:
                extension = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}[file.image.format]
                key = f"vehiculos/{vehicle.pk}/{uuid4().hex}.{extension}"
                # Include the attempted key so a timed-out upload can also be cleaned up.
                uploaded.append(key)
                try:
                    upload_document(file, key)
                except Exception as exc:
                    logger.exception("No se pudo subir la fotografía de un vehículo")
                    raise APIException("No se pudieron guardar las fotos. El vehículo mantiene su estado anterior. Reintenta.") from exc

            with transaction.atomic():
                vehicle = get_object_or_404(Vehiculo.objects.select_for_update(), pk=vehicle.pk)
                existing = self.existing_movement(vehicle, data)
                if existing:
                    return Response(MovimientoSerializer(existing).data)
                self.validate_state(vehicle, data)
                # Compare-and-swap also guards against stale clients and databases without row locks.
                changed = Vehiculo.objects.filter(pk=vehicle.pk, version=data["version"]).update(
                    supervisor_actual=request.user if data["tipo"] == "recepcion" else None,
                    kilometraje_actual=data["kilometraje"], version=F("version") + 1,
                )
                if not changed:
                    raise Conflict()
                reception = None
                if data["tipo"] == "entrega":
                    reception = vehicle.movimientos.filter(tipo="recepcion", entrega__isnull=True,
                                                           supervisor=request.user).first()
                    if not reception:
                        raise Conflict("No se encontró una recepción pendiente de entrega.")
                values = {key: value for key, value in data.items() if key not in {"version", "fotos"}}
                values["resumen"] = data["resumen"].strip() or (
                    "Recepción sin observaciones" if data["tipo"] == "recepcion" else "Entrega sin observaciones"
                )
                movement = MovimientoVehiculo.objects.create(
                    vehiculo=vehicle, supervisor=request.user, supervisor_nombre=str(request.user),
                    recepcion=reception, **values,
                )
                FotoVehiculo.objects.bulk_create([
                    FotoVehiculo(movimiento=movement, storage_key=key, **photo)
                    for key, photo in zip(uploaded, metadata)
                ])
            committed = True
            return Response(MovimientoSerializer(movement).data, status=201)
        except IntegrityError as exc:
            raise Conflict() from exc
        finally:
            if not committed:
                for key in uploaded:
                    try:
                        delete_document(key)
                    except Exception:
                        logger.exception("No se pudo limpiar la fotografía %s", key)
