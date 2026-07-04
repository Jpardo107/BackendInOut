from django.db import models
from django.db import transaction
from django.utils import timezone
from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from .models import MovimientoInventario, PrendaInventario
from .permissions import IsInventarioRole
from .serializers import MovimientoInventarioSerializer, PrendaInventarioSerializer


def user_has_inventory_admin_role(user):
    cargo = getattr(getattr(user, "cargo", None), "nombre", "") or ""
    cargo = cargo.strip().lower()
    return bool(
        user
        and user.is_authenticated
        and (
            user.is_staff
            or user.is_superuser
            or any(role in cargo for role in ("rrhh", "administrador", "administrativo", "admin"))
        )
    )


def normalize_scanned_code(value):
    code = str(value or "").strip()
    if not code:
        return ""
    return code.rstrip("/").split("/")[-1] if "/" in code else code


class PrendaInventarioViewSet(viewsets.ModelViewSet):
    serializer_class = PrendaInventarioSerializer
    permission_classes = [IsInventarioRole]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        "nombre_prenda",
        "talla_prenda",
        "codigo_barra",
        "codigo_qr",
    ]
    ordering_fields = [
        "nombre_prenda",
        "talla_prenda",
        "stock_actual",
        "stock_critico",
        "actualizado_en",
    ]
    ordering = ["nombre_normalizado", "talla_normalizada"]

    def get_queryset(self):
        queryset = PrendaInventario.objects.all()
        activo = self.request.query_params.get("activo")
        bajo_stock = self.request.query_params.get("bajo_stock")

        if activo is not None:
            queryset = queryset.filter(activo=activo.lower() in ("1", "true", "si", "yes"))

        if bajo_stock is not None and bajo_stock.lower() in ("1", "true", "si", "yes"):
            queryset = queryset.filter(stock_actual__lte=models.F("stock_critico"))

        return queryset

    @action(detail=False, methods=["get"], url_path="buscar-codigo")
    def buscar_codigo(self, request):
        codigo = request.query_params.get("codigo", "")
        codigo_normalizado = normalize_scanned_code(codigo)

        if not codigo_normalizado:
            raise ValidationError({"codigo": "Debes indicar un codigo para buscar."})

        prenda = (
            self.get_queryset()
            .filter(
                models.Q(codigo_barra__iexact=codigo)
                | models.Q(codigo_qr__iexact=codigo)
                | models.Q(codigo_barra__iexact=codigo_normalizado)
                | models.Q(codigo_qr__iendswith=f"/{codigo_normalizado}")
            )
            .first()
        )

        if not prenda:
            raise NotFound("No existe una prenda asociada al codigo escaneado.")

        return Response(self.get_serializer(prenda).data)


class MovimientoInventarioViewSet(viewsets.ModelViewSet):
    serializer_class = MovimientoInventarioSerializer
    permission_classes = [IsInventarioRole]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        "prenda__nombre_prenda",
        "prenda__talla_prenda",
        "prenda__codigo_barra",
        "observacion",
    ]
    ordering_fields = ["creado_en", "tipo", "cantidad"]
    ordering = ["-creado_en", "-id"]

    def get_queryset(self):
        queryset = (
            MovimientoInventario.objects
            .select_related("prenda", "usuario_registro", "usuario_final", "destinatario_personal")
        )
        tipo = self.request.query_params.get("tipo")
        prenda_id = self.request.query_params.get("prenda")
        estado_envio = self.request.query_params.get("estado_envio")
        usuario_final = self.request.query_params.get("usuario_final")

        if tipo:
            queryset = queryset.filter(tipo=tipo)

        if prenda_id:
            queryset = queryset.filter(prenda_id=prenda_id)

        if estado_envio:
            queryset = queryset.filter(estado_envio=estado_envio)

        if usuario_final:
            if usuario_final == "me":
                queryset = queryset.filter(usuario_final=self.request.user)
            else:
                queryset = queryset.filter(usuario_final_id=usuario_final)

        return queryset

    @action(detail=True, methods=["patch"], url_path="cambiar-estado")
    def cambiar_estado(self, request, pk=None):
        nuevo_estado = request.data.get("estado_envio")
        observacion = str(request.data.get("observacion") or "").strip()
        estados_permitidos = {
            MovimientoInventario.ESTADO_RECIBIDO,
            MovimientoInventario.ESTADO_DEVUELTO,
            MovimientoInventario.ESTADO_CANCELADO,
        }

        if nuevo_estado not in estados_permitidos:
            raise ValidationError({
                "estado_envio": "Estado invalido. Usa recibido, devuelto o cancelado."
            })

        with transaction.atomic():
            movimiento = (
                MovimientoInventario.objects
                .select_for_update()
                .select_related("prenda", "usuario_final", "usuario_registro")
                .get(pk=pk)
            )

            if movimiento.tipo != MovimientoInventario.TIPO_ENTREGA:
                raise ValidationError({"detail": "Solo las entregas tienen estado de envio."})

            if (
                not user_has_inventory_admin_role(request.user)
                and movimiento.usuario_final_id != request.user.id
            ):
                raise ValidationError({"detail": "No puedes gestionar una entrega asignada a otro supervisor."})

            if movimiento.estado_envio != MovimientoInventario.ESTADO_EN_TRANSITO:
                raise ValidationError({
                    "estado_envio": "Solo una entrega en transito puede cambiar de estado."
                })

            movimiento.estado_envio = nuevo_estado
            movimiento.fecha_estado_envio = timezone.now()

            if observacion:
                movimiento.observacion = (
                    f"{movimiento.observacion}\n{observacion}".strip()
                    if movimiento.observacion else observacion
                )

            movimiento.save(update_fields=["estado_envio", "fecha_estado_envio", "observacion"])

            if nuevo_estado in (
                MovimientoInventario.ESTADO_DEVUELTO,
                MovimientoInventario.ESTADO_CANCELADO,
            ):
                prenda = PrendaInventario.objects.select_for_update().get(pk=movimiento.prenda_id)
                stock_antes = prenda.stock_actual
                stock_despues = stock_antes + movimiento.cantidad
                prenda.stock_actual = stock_despues
                prenda.save(update_fields=["stock_actual", "actualizado_en"])

                MovimientoInventario.objects.create(
                    prenda=prenda,
                    tipo=MovimientoInventario.TIPO_RECEPCION,
                    cantidad=movimiento.cantidad,
                    stock_antes=stock_antes,
                    stock_despues=stock_despues,
                    usuario_registro=request.user,
                    usuario_final=movimiento.usuario_final,
                    destinatario_personal=movimiento.destinatario_personal,
                    observacion=f"Retorno por entrega {movimiento.id}: {nuevo_estado}",
                    estado_envio=MovimientoInventario.ESTADO_NO_APLICA,
                )

        return Response({
            "id": movimiento.id,
            "estado_envio": movimiento.estado_envio,
            "fecha_estado_envio": movimiento.fecha_estado_envio,
            "observacion": movimiento.observacion,
        })
