from django.db import transaction
from rest_framework import serializers

from documentacion.services.r2_storage import generate_signed_url

from .models import ConfiguracionAlertaStock, ComprobanteEntregaInventario, MovimientoInventario, PrendaInventario
from .services.codigos import generar_codigo_barra, generar_codigo_qr, normalizar_texto
from .services.stock_alertas import alcanzo_stock_critico, enviar_alerta_stock


class PrendaInventarioSerializer(serializers.ModelSerializer):
    bajo_stock_critico = serializers.BooleanField(read_only=True)

    class Meta:
        model = PrendaInventario
        fields = [
            "id",
            "nombre_prenda",
            "talla_prenda",
            "cantidad_prenda",
            "stock_critico",
            "stock_actual",
            "codigo_barra",
            "codigo_qr",
            "bajo_stock_critico",
            "activo",
            "creado_en",
            "actualizado_en",
        ]
        read_only_fields = ["id", "codigo_barra", "codigo_qr", "creado_en", "actualizado_en"]

    def validate(self, attrs):
        nombre_prenda = attrs.get("nombre_prenda", getattr(self.instance, "nombre_prenda", ""))
        talla_prenda = attrs.get("talla_prenda", getattr(self.instance, "talla_prenda", ""))

        if not str(nombre_prenda).strip():
            raise serializers.ValidationError({"nombre_prenda": "El nombre de la prenda es obligatorio."})

        if not str(talla_prenda).strip():
            raise serializers.ValidationError({"talla_prenda": "La talla de la prenda es obligatoria."})

        nombre_normalizado = normalizar_texto(nombre_prenda)
        talla_normalizada = normalizar_texto(talla_prenda)
        queryset = PrendaInventario.objects.filter(
            nombre_normalizado=nombre_normalizado,
            talla_normalizada=talla_normalizada,
        )

        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)

        if queryset.exists():
            raise serializers.ValidationError(
                {"detail": "Ya existe una prenda con ese nombre y talla."}
            )

        return attrs

    def create(self, validated_data):
        codigo_barra = generar_codigo_barra(
            validated_data["nombre_prenda"],
            validated_data["talla_prenda"],
        )
        validated_data["codigo_barra"] = codigo_barra
        validated_data["codigo_qr"] = generar_codigo_qr(codigo_barra)
        validated_data.setdefault("cantidad_prenda", validated_data.get("stock_actual", 0))
        return super().create(validated_data)


class MovimientoInventarioSerializer(serializers.ModelSerializer):
    prenda_detalle = PrendaInventarioSerializer(source="prenda", read_only=True)
    usuario_registro_nombre = serializers.SerializerMethodField()
    usuario_final_nombre = serializers.SerializerMethodField()
    destinatario_nombre = serializers.SerializerMethodField()
    destinatario_rut = serializers.SerializerMethodField()
    destinatario_ubicacion = serializers.SerializerMethodField()
    comprobante_entrega_id = serializers.SerializerMethodField()
    comprobante_descarga_url = serializers.SerializerMethodField()

    class Meta:
        model = MovimientoInventario
        fields = [
            "id",
            "prenda",
            "prenda_detalle",
            "tipo",
            "cantidad",
            "stock_antes",
            "stock_despues",
            "usuario_registro",
            "usuario_registro_nombre",
            "usuario_final",
            "usuario_final_nombre",
            "destinatario_personal",
            "destinatario_nombre",
            "destinatario_rut",
            "destinatario_ubicacion",
            "comprobante_entrega_id",
            "comprobante_descarga_url",
            "observacion",
            "estado_envio",
            "fecha_estado_envio",
            "creado_en",
        ]
        read_only_fields = [
            "id",
            "stock_antes",
            "stock_despues",
            "usuario_registro",
            "usuario_registro_nombre",
            "usuario_final_nombre",
            "destinatario_nombre",
            "destinatario_rut",
            "destinatario_ubicacion",
            "comprobante_entrega_id",
            "comprobante_descarga_url",
            "fecha_estado_envio",
            "creado_en",
        ]

    def get_usuario_registro_nombre(self, obj):
        if not obj.usuario_registro:
            return None
        return f"{obj.usuario_registro.nombres} {obj.usuario_registro.apellidos}"

    def get_usuario_final_nombre(self, obj):
        if not obj.usuario_final:
            return None
        return f"{obj.usuario_final.nombres} {obj.usuario_final.apellidos}"

    def get_destinatario_nombre(self, obj):
        return obj.destinatario_personal.nombre_completo if obj.destinatario_personal else None

    def get_destinatario_rut(self, obj):
        return obj.destinatario_personal.rut if obj.destinatario_personal else None

    def get_destinatario_ubicacion(self, obj):
        return obj.destinatario_personal.ubicacion if obj.destinatario_personal else None

    def get_comprobante_entrega_id(self, obj):
        comprobante = obj.comprobantes_entrega.order_by("-creado_en", "-id").first()
        return comprobante.id if comprobante else None

    def get_comprobante_descarga_url(self, obj):
        comprobante = obj.comprobantes_entrega.order_by("-creado_en", "-id").first()
        if not comprobante:
            return ""
        try:
            return generate_signed_url(
                comprobante.storage_key,
                expires=600,
                filename=comprobante.nombre_original or f"comprobante-entrega-{comprobante.id}.pdf",
                disposition="attachment",
            )
        except Exception:
            return ""

    def validate(self, attrs):
        tipo = attrs.get("tipo")
        cantidad = attrs.get("cantidad", 0)

        if cantidad <= 0:
            raise serializers.ValidationError({"cantidad": "La cantidad debe ser mayor a cero."})

        observacion = (attrs.get("observacion") or "").strip().lower()
        entrega_a_operaciones = observacion == "operaciones"
        entrega_directa = observacion == "entrega directa a solicitante"

        if (
            tipo == MovimientoInventario.TIPO_ENTREGA
            and not attrs.get("usuario_final")
            and not entrega_a_operaciones
            and not (entrega_directa and attrs.get("destinatario_personal"))
        ):
            raise serializers.ValidationError(
                {
                    "usuario_final": (
                        "La entrega debe indicar supervisor, Operaciones "
                        "o entrega directa a solicitante."
                    )
                }
            )

        return attrs

    def create(self, validated_data):
        request = self.context.get("request")

        with transaction.atomic():
            prenda = PrendaInventario.objects.select_for_update().get(pk=validated_data["prenda"].pk)
            tipo = validated_data["tipo"]
            cantidad = validated_data["cantidad"]
            stock_antes = prenda.stock_actual
            estado_envio = MovimientoInventario.ESTADO_NO_APLICA

            if tipo == MovimientoInventario.TIPO_ENTREGA:
                if cantidad > stock_antes:
                    raise serializers.ValidationError(
                        {"cantidad": "No hay stock suficiente para registrar la entrega."}
                    )
                stock_despues = stock_antes - cantidad
                estado_envio = MovimientoInventario.ESTADO_EN_TRANSITO
            elif tipo in (MovimientoInventario.TIPO_INGRESO, MovimientoInventario.TIPO_RECEPCION):
                stock_despues = stock_antes + cantidad
            else:
                stock_despues = cantidad

            prenda.stock_actual = stock_despues
            prenda.save(update_fields=["stock_actual", "actualizado_en"])

            movimiento = MovimientoInventario.objects.create(
                **validated_data,
                stock_antes=stock_antes,
                stock_despues=stock_despues,
                estado_envio=estado_envio,
                usuario_registro=request.user if request else None,
            )
            if (
                tipo == MovimientoInventario.TIPO_ENTREGA
                and alcanzo_stock_critico(stock_antes, stock_despues, prenda.stock_critico)
            ):
                transaction.on_commit(lambda: enviar_alerta_stock(
                    prenda.id,
                    stock_despues,
                    prenda.stock_critico,
                    movimiento.id,
                ))
            return movimiento


class ComprobanteEntregaInventarioSerializer(serializers.ModelSerializer):
    descarga_url = serializers.SerializerMethodField()
    movimientos_ids = serializers.PrimaryKeyRelatedField(
        source="movimientos",
        many=True,
        read_only=True,
    )
    destinatario_nombre = serializers.SerializerMethodField()
    supervisor_nombre = serializers.SerializerMethodField()

    class Meta:
        model = ComprobanteEntregaInventario
        fields = [
            "id",
            "movimientos_ids",
            "destinatario_personal",
            "destinatario_nombre",
            "supervisor",
            "supervisor_nombre",
            "storage_key",
            "nombre_original",
            "mime_type",
            "size",
            "descarga_url",
            "creado_en",
        ]
        read_only_fields = fields

    def get_descarga_url(self, obj):
        try:
            return generate_signed_url(
                obj.storage_key,
                expires=600,
                filename=obj.nombre_original or f"comprobante-entrega-{obj.id}.pdf",
                disposition="attachment",
            )
        except Exception:
            return ""

    def get_destinatario_nombre(self, obj):
        return obj.destinatario_personal.nombre_completo if obj.destinatario_personal else None

    def get_supervisor_nombre(self, obj):
        if not obj.supervisor:
            return None
        return f"{obj.supervisor.nombres} {obj.supervisor.apellidos}"


class ConfiguracionAlertaStockSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfiguracionAlertaStock
        fields = ("email_1", "email_2", "actualizado_en")
        read_only_fields = ("actualizado_en",)

    def validate(self, attrs):
        email_1 = str(attrs.get("email_1", getattr(self.instance, "email_1", "")) or "").strip().lower()
        email_2 = str(attrs.get("email_2", getattr(self.instance, "email_2", "")) or "").strip().lower()
        if email_1 and email_2 and email_1 == email_2:
            raise serializers.ValidationError({"email_2": "Los correos destinatarios deben ser diferentes."})
        attrs["email_1"] = email_1
        attrs["email_2"] = email_2
        return attrs
