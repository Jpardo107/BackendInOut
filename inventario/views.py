import json
from datetime import datetime, time

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import models
from django.db import transaction
from django.db.utils import OperationalError, ProgrammingError
from django.utils.dateparse import parse_date, parse_datetime
from django.utils import timezone
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from documentacion.services.r2_storage import generate_signed_url, upload_document
from user.models import PersonalEmpresa

from .models import (
    AutorizacionEntregaInventario,
    ConfiguracionAlertaStock,
    ComprobanteEntregaInventario,
    MovimientoInventario,
    PrendaInventario,
    RegistroAlertaStock,
    comprobante_entrega_upload_key,
)
from .permissions import IsInventarioRole
from .serializers import (
    ConfiguracionAlertaStockSerializer,
    ComprobanteEntregaInventarioSerializer,
    MovimientoInventarioSerializer,
    PrendaInventarioSerializer,
)


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


def get_cargo_name(user):
    return (getattr(getattr(user, "cargo", None), "nombre", "") or "").strip()


def get_cargo_key(user):
    return get_cargo_name(user).lower()


def user_is_rrhh(user):
    return "rrhh" in get_cargo_key(user)


def user_is_supervisor(user):
    return "supervisor" in get_cargo_key(user)


def user_can_manage_delivery_authorizations(user):
    cargo = get_cargo_key(user)
    return bool(
        user
        and user.is_authenticated
        and (
            (user.is_superuser and "tecnico" in cargo)
            or "encargado rrhh" in cargo
        )
    )


def user_is_delivery_authorization_candidate(user):
    cargo = get_cargo_key(user)
    return any(role in cargo for role in ("gerente", "operaciones", "supervisor", "rrhh"))


def user_can_deliver_inventory(user):
    if not user or not user.is_authenticated:
        return False
    # RRHH y Supervisores pueden concretar entregas por las funciones propias de su cargo.
    if user.is_staff or user.is_superuser or user_is_rrhh(user) or user_is_supervisor(user):
        return True
    if not user_is_delivery_authorization_candidate(user):
        return False
    try:
        return AutorizacionEntregaInventario.objects.filter(usuario=user, autorizado=True).exists()
    except (OperationalError, ProgrammingError):
        return False


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

    @action(detail=False, methods=["post"], url_path="registro-manual")
    def registro_manual(self, request):
        if not user_has_inventory_admin_role(request.user):
            raise ValidationError({"detail": "No tienes permisos para registrar entregas manuales."})

        prenda_id = request.data.get("prenda")
        destinatario_id = request.data.get("destinatario_personal")
        cantidad_raw = request.data.get("cantidad")
        fecha_raw = str(request.data.get("fecha_entrega") or "").strip()
        observacion = str(request.data.get("observacion") or "").strip()

        try:
            cantidad = int(cantidad_raw)
        except (TypeError, ValueError):
            raise ValidationError({"cantidad": "La cantidad debe ser un numero entero."})

        if cantidad <= 0:
            raise ValidationError({"cantidad": "La cantidad debe ser mayor a cero."})

        fecha_entrega = parse_datetime(fecha_raw)
        if fecha_entrega is None:
            fecha_date = parse_date(fecha_raw)
            if fecha_date:
                fecha_entrega = datetime.combine(fecha_date, time.min)

        if fecha_entrega is None:
            raise ValidationError({"fecha_entrega": "Indica una fecha de entrega valida."})

        if timezone.is_naive(fecha_entrega):
            fecha_entrega = timezone.make_aware(fecha_entrega, timezone.get_current_timezone())

        if fecha_entrega > timezone.now():
            raise ValidationError({"fecha_entrega": "La fecha de entrega no puede ser futura."})

        try:
            destinatario = PersonalEmpresa.objects.get(pk=destinatario_id, activo=True)
        except PersonalEmpresa.DoesNotExist:
            raise ValidationError({"destinatario_personal": "Selecciona una persona activa."})

        with transaction.atomic():
            try:
                prenda = PrendaInventario.objects.select_for_update().get(pk=prenda_id, activo=True)
            except PrendaInventario.DoesNotExist:
                raise ValidationError({"prenda": "Selecciona una prenda activa."})

            stock_antes = prenda.stock_actual
            stock_despues = stock_antes

            detalle_observacion = "Ingreso manual informativo sin firma"
            if observacion:
                detalle_observacion = f"{detalle_observacion}: {observacion}"

            movimiento = MovimientoInventario.objects.create(
                prenda=prenda,
                tipo=MovimientoInventario.TIPO_ENTREGA,
                cantidad=cantidad,
                stock_antes=stock_antes,
                stock_despues=stock_despues,
                usuario_registro=request.user,
                destinatario_personal=destinatario,
                observacion=detalle_observacion,
                estado_envio=MovimientoInventario.ESTADO_RECIBIDO,
                fecha_estado_envio=fecha_entrega,
            )
            MovimientoInventario.objects.filter(pk=movimiento.pk).update(creado_en=fecha_entrega)
            movimiento.refresh_from_db()

        serializer = self.get_serializer(movimiento)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

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

        if nuevo_estado == MovimientoInventario.ESTADO_RECIBIDO and not user_can_deliver_inventory(request.user):
            raise ValidationError({"detail": "No estas autorizado para entregar inventario."})

        try:
            movimiento = (
                MovimientoInventario.objects
                .select_related("prenda", "usuario_final", "usuario_registro")
                .get(pk=pk)
            )
        except MovimientoInventario.DoesNotExist:
            raise NotFound("No existe el movimiento de inventario indicado.")

        response_data = {
            "id": movimiento.id,
            "estado_envio": movimiento.estado_envio,
            "fecha_estado_envio": movimiento.fecha_estado_envio,
            "observacion": movimiento.observacion,
        }

        if movimiento.tipo != MovimientoInventario.TIPO_ENTREGA:
            raise ValidationError({"detail": "Solo las entregas tienen estado de envio."})

        if (
            not user_has_inventory_admin_role(request.user)
            and movimiento.usuario_final_id != request.user.id
        ):
            raise ValidationError({"detail": "No puedes gestionar una entrega asignada a otro supervisor."})

        if movimiento.estado_envio == nuevo_estado:
            return Response(response_data)

        if movimiento.estado_envio in (
            MovimientoInventario.ESTADO_RECIBIDO,
            MovimientoInventario.ESTADO_DEVUELTO,
            MovimientoInventario.ESTADO_CANCELADO,
        ):
            raise ValidationError(
                {"estado_envio": "Esta entrega ya fue gestionada y no puede cambiar nuevamente."}
            )

        if movimiento.estado_envio != MovimientoInventario.ESTADO_EN_TRANSITO:
            raise ValidationError(
                {"estado_envio": "Solo una entrega en transito puede cambiar de estado."}
            )

        fecha_estado = timezone.now()
        nueva_observacion = movimiento.observacion
        if observacion:
            nueva_observacion = (
                f"{movimiento.observacion}\n{observacion}".strip()
                if movimiento.observacion else observacion
            )

        if nuevo_estado == MovimientoInventario.ESTADO_RECIBIDO:
            MovimientoInventario.objects.filter(pk=movimiento.pk).update(
                estado_envio=nuevo_estado,
                fecha_estado_envio=fecha_estado,
                observacion=nueva_observacion,
            )
            return Response({
                "id": movimiento.id,
                "estado_envio": nuevo_estado,
                "fecha_estado_envio": fecha_estado,
                "observacion": nueva_observacion,
            })

        with transaction.atomic():
            updated = MovimientoInventario.objects.filter(
                pk=movimiento.pk,
                estado_envio=MovimientoInventario.ESTADO_EN_TRANSITO,
            ).update(
                estado_envio=nuevo_estado,
                fecha_estado_envio=fecha_estado,
                observacion=nueva_observacion,
            )

            if not updated:
                raise ValidationError(
                    {"estado_envio": "Esta entrega ya fue gestionada por otro proceso."}
                )

            try:
                prenda = PrendaInventario.objects.select_for_update().get(pk=movimiento.prenda_id)
            except PrendaInventario.DoesNotExist:
                raise NotFound("No existe la prenda asociada al movimiento.")
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
            "estado_envio": nuevo_estado,
            "fecha_estado_envio": fecha_estado,
            "observacion": nueva_observacion,
        })


class ComprobanteEntregaInventarioViewSet(viewsets.ModelViewSet):
    serializer_class = ComprobanteEntregaInventarioSerializer
    permission_classes = [IsInventarioRole]
    parser_classes = [MultiPartParser, FormParser]
    http_method_names = ["get", "post", "head", "options"]
    ordering = ["-creado_en", "-id"]

    def get_queryset(self):
        return (
            ComprobanteEntregaInventario.objects
            .select_related("destinatario_personal", "supervisor")
            .prefetch_related("movimientos")
        )

    def create(self, request, *args, **kwargs):
        archivo = request.FILES.get("archivo")
        movimientos_raw = request.data.get("movimientos", "")

        if not archivo:
            raise ValidationError({"archivo": "Debes adjuntar el PDF del comprobante."})

        if getattr(archivo, "content_type", "") != "application/pdf":
            raise ValidationError({"archivo": "El comprobante debe ser un archivo PDF."})

        try:
            movimientos_ids = json.loads(movimientos_raw) if isinstance(movimientos_raw, str) else movimientos_raw
        except json.JSONDecodeError:
            movimientos_ids = []

        if not isinstance(movimientos_ids, list) or not movimientos_ids:
            raise ValidationError({"movimientos": "Debes indicar los movimientos incluidos en el comprobante."})

        movimientos = list(
            MovimientoInventario.objects
            .select_related("destinatario_personal", "usuario_final")
            .filter(id__in=movimientos_ids, tipo=MovimientoInventario.TIPO_ENTREGA)
        )

        if len(movimientos) != len(set(movimientos_ids)):
            raise ValidationError({"movimientos": "Uno o más movimientos no existen o no son entregas."})

        destinatario = next((movimiento.destinatario_personal for movimiento in movimientos if movimiento.destinatario_personal), None)
        supervisor = next((movimiento.usuario_final for movimiento in movimientos if movimiento.usuario_final), None)
        nombre_original = getattr(archivo, "name", "") or "comprobante-entrega.pdf"
        storage_key = comprobante_entrega_upload_key(nombre_original)
        upload_document(archivo, storage_key)

        comprobante = ComprobanteEntregaInventario.objects.create(
            destinatario_personal=destinatario,
            supervisor=supervisor or request.user,
            storage_key=storage_key,
            nombre_original=nombre_original,
            mime_type=getattr(archivo, "content_type", "") or "application/pdf",
            size=getattr(archivo, "size", 0) or 0,
        )
        comprobante.movimientos.set(movimientos)

        serializer = self.get_serializer(comprobante)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="descargar")
    def descargar(self, request, pk=None):
        comprobante = self.get_object()
        try:
            url = generate_signed_url(
                comprobante.storage_key,
                expires=600,
                filename=comprobante.nombre_original or f"comprobante-entrega-{comprobante.id}.pdf",
                disposition="attachment",
            )
        except Exception:
            raise ValidationError({"detail": "No se pudo generar el enlace de descarga del comprobante."})

        return Response({"url": url})


class AutorizadosEntregaInventarioView(APIView):
    permission_classes = [IsInventarioRole]

    def get(self, request):
        usuarios = (
            request.user.__class__.objects
            .select_related("cargo")
            .filter(is_active=True)
            .filter(
                models.Q(cargo__nombre__icontains="gerente")
                | models.Q(cargo__nombre__icontains="operaciones")
                | models.Q(cargo__nombre__icontains="supervisor")
                | models.Q(cargo__nombre__icontains="rrhh")
            )
            .order_by("nombres", "apellidos")
        )
        try:
            autorizaciones = {
                item.usuario_id: item
                for item in AutorizacionEntregaInventario.objects.filter(usuario__in=usuarios)
            }
        except (OperationalError, ProgrammingError):
            autorizaciones = {}

        return Response([
            {
                "id": usuario.id,
                "nombre": f"{usuario.nombres} {usuario.apellidos}".strip(),
                "username": usuario.username,
                "email": usuario.email,
                "cargo": get_cargo_name(usuario),
                "autorizado": True if (user_is_rrhh(usuario) or user_is_supervisor(usuario)) else bool(autorizaciones.get(usuario.id) and autorizaciones[usuario.id].autorizado),
                "obligatorio": user_is_rrhh(usuario) or user_is_supervisor(usuario),
                "editable": not (user_is_rrhh(usuario) or user_is_supervisor(usuario)),
            }
            for usuario in usuarios
        ])

    def post(self, request):
        usuario_id = request.data.get("usuario")
        autorizado = bool(request.data.get("autorizado"))
        password = str(request.data.get("password") or "")

        if not request.user.check_password(password):
            raise ValidationError({"password": "La autenticacion no es valida."})

        if not user_can_manage_delivery_authorizations(request.user):
            raise ValidationError({"detail": "Solo el tecnico superadmin o el encargado de RRHH puede modificar autorizaciones."})

        try:
            usuario = request.user.__class__.objects.select_related("cargo").get(pk=usuario_id, is_active=True)
        except request.user.__class__.DoesNotExist:
            raise NotFound("No existe el usuario indicado.")

        if user_is_rrhh(usuario) or user_is_supervisor(usuario):
            raise ValidationError({"usuario": "RRHH y Supervisores siempre estan autorizados por su cargo."})

        if not user_is_delivery_authorization_candidate(usuario):
            raise ValidationError({"usuario": "Solo gerentes, operaciones y supervisores pueden ser autorizados."})

        try:
            autorizacion, _ = AutorizacionEntregaInventario.objects.update_or_create(
                usuario=usuario,
                defaults={
                    "autorizado": autorizado,
                    "actualizado_por": request.user,
                },
            )
        except (OperationalError, ProgrammingError):
            raise ValidationError({"detail": "La tabla de autorizaciones no existe. Ejecuta las migraciones del backend."})

        return Response({
            "id": usuario.id,
            "nombre": f"{usuario.nombres} {usuario.apellidos}".strip(),
            "username": usuario.username,
            "email": usuario.email,
            "cargo": get_cargo_name(usuario),
            "autorizado": autorizacion.autorizado,
            "obligatorio": False,
            "editable": True,
        })


class ConfiguracionAlertaStockView(APIView):
    permission_classes = [IsInventarioRole]

    def get_object(self):
        configuracion, _ = ConfiguracionAlertaStock.objects.get_or_create(pk=1)
        return configuracion

    def get(self, request):
        data = ConfiguracionAlertaStockSerializer(self.get_object()).data
        ultimo = RegistroAlertaStock.objects.select_related("prenda").first()
        data["ultimo_intento"] = (
            {
                "prenda": f"{ultimo.prenda.nombre_prenda} / {ultimo.prenda.talla_prenda}",
                "stock_actual": ultimo.stock_actual,
                "stock_critico": ultimo.stock_critico,
                "destinatarios": ultimo.destinatarios,
                "enviado": ultimo.enviado,
                "error": ultimo.error,
                "creado_en": ultimo.creado_en,
            }
            if ultimo else None
        )
        return Response(data)

    def put(self, request):
        if not user_has_inventory_admin_role(request.user):
            raise PermissionDenied("Solo usuarios administrativos pueden configurar alertas de stock.")
        configuracion = self.get_object()
        serializer = ConfiguracionAlertaStockSerializer(configuracion, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(actualizado_por=request.user)
        return Response(serializer.data)

    patch = put

    def post(self, request):
        if not user_has_inventory_admin_role(request.user):
            raise PermissionDenied("Solo usuarios administrativos pueden probar alertas de stock.")

        destinatarios = self.get_object().destinatarios
        if not destinatarios:
            raise ValidationError({"detail": "Guarda al menos un correo destinatario antes de realizar la prueba."})

        try:
            message = EmailMultiAlternatives(
                subject="PRUEBA: Alertas de stock INOUT",
                body=(
                    "Este es un correo de prueba del sistema de alertas de stock de INOUT.\n\n"
                    "La configuración de correo está operativa."
                ),
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                to=destinatarios,
            )
            message.attach_alternative(
                '<div style="font-family:Arial,sans-serif;color:#1f2937;max-width:620px">'
                '<div style="background:#193040;color:white;padding:16px 20px;font-size:18px;font-weight:bold">'
                'Prueba de alertas de stock INOUT</div>'
                '<div style="border:1px solid #d9e2ec;padding:20px">'
                '<p>La configuración de correo está operativa.</p></div></div>',
                "text/html",
            )
            enviados = message.send(fail_silently=False)
            if enviados != 1:
                raise RuntimeError("El servidor de correo no confirmó el envío.")
        except Exception as exc:
            return Response(
                {"detail": f"No fue posible enviar el correo de prueba: {str(exc)[:500]}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response({"detail": "Correo de prueba enviado.", "destinatarios": destinatarios})
