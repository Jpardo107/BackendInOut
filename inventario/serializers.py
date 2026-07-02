from django.db import transaction
from rest_framework import serializers

from .models import MovimientoInventario, PrendaInventario
from .services.codigos import generar_codigo_barra, generar_codigo_qr, normalizar_texto


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
            "observacion",
            "creado_en",
        ]
        read_only_fields = [
            "id",
            "stock_antes",
            "stock_despues",
            "usuario_registro",
            "usuario_registro_nombre",
            "usuario_final_nombre",
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

    def validate(self, attrs):
        tipo = attrs.get("tipo")
        cantidad = attrs.get("cantidad", 0)

        if cantidad <= 0:
            raise serializers.ValidationError({"cantidad": "La cantidad debe ser mayor a cero."})

        observacion = (attrs.get("observacion") or "").strip().lower()
        entrega_a_operaciones = observacion == "operaciones"

        if (
            tipo == MovimientoInventario.TIPO_ENTREGA
            and not attrs.get("usuario_final")
            and not entrega_a_operaciones
        ):
            raise serializers.ValidationError(
                {"usuario_final": "La entrega debe indicar el supervisor receptor u Operaciones."}
            )

        return attrs

    def create(self, validated_data):
        request = self.context.get("request")

        with transaction.atomic():
            prenda = PrendaInventario.objects.select_for_update().get(pk=validated_data["prenda"].pk)
            tipo = validated_data["tipo"]
            cantidad = validated_data["cantidad"]
            stock_antes = prenda.stock_actual

            if tipo == MovimientoInventario.TIPO_ENTREGA:
                if cantidad > stock_antes:
                    raise serializers.ValidationError(
                        {"cantidad": "No hay stock suficiente para registrar la entrega."}
                    )
                stock_despues = stock_antes - cantidad
            elif tipo in (MovimientoInventario.TIPO_INGRESO, MovimientoInventario.TIPO_RECEPCION):
                stock_despues = stock_antes + cantidad
            else:
                stock_despues = cantidad

            prenda.stock_actual = stock_despues
            prenda.save(update_fields=["stock_actual", "actualizado_en"])

            return MovimientoInventario.objects.create(
                **validated_data,
                stock_antes=stock_antes,
                stock_despues=stock_despues,
                usuario_registro=request.user if request else None,
            )
