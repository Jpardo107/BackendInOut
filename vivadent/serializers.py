from django.db import transaction
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import AnalyticsEvent, Promotion, SiteImage, SiteText, StoreCollection, StoreSession


class VivadentTokenSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        access = getattr(self.user, "vivadent_access", None)
        if not access or not access.active:
            raise serializers.ValidationError("Este usuario no tiene acceso a Vivadent.")
        data["user"] = {"id": self.user.id, "username": self.user.username, "name": f"{self.user.nombres} {self.user.apellidos}".strip(), "email": self.user.email}
        return data


class PromotionSerializer(serializers.ModelSerializer):
    section_keys = serializers.ListField(child=serializers.ChoiceField(choices=['tienda', 'dental', 'facial', 'radiologia']), required=False, allow_empty=True)

    def validate_section_keys(self, keys):
        if len(keys) != len(set(keys)):
            raise serializers.ValidationError("No puedes repetir secciones.")
        if StoreCollection.objects.filter(key__in=keys).count() != len(keys):
            raise serializers.ValidationError("Actualiza las secciones del backend antes de guardar.")
        return keys

    def to_representation(self, instance):
        # Membership is stored by collection; never infer it from the title here.
        data = super().to_representation(instance)
        collections = self.context.get('store_collections')
        if collections is None:
            collections = StoreCollection.objects.all()
        data['section_keys'] = [c.key for c in collections if instance.id in c.promotion_ids and c.key in ['tienda', 'dental', 'facial', 'radiologia']]
        return data

    def sync_sections(self, instance, keys):
        if keys is None:
            return
        for collection in StoreCollection.objects.select_for_update().filter(key__in=['tienda', 'dental', 'facial', 'radiologia']):
            ids = list(collection.promotion_ids)
            if collection.key in keys and instance.id not in ids:
                ids.append(instance.id)
            elif collection.key not in keys:
                ids = [pk for pk in ids if pk != instance.id]
            if ids != collection.promotion_ids:
                collection.promotion_ids = ids
                collection.save(update_fields=['promotion_ids', 'updated_at'])

    @transaction.atomic
    def create(self, validated_data):
        keys = validated_data.pop('section_keys', None)
        instance = super().create(validated_data)
        self.sync_sections(instance, keys)
        return instance

    @transaction.atomic
    def update(self, instance, validated_data):
        keys = validated_data.pop('section_keys', None)
        instance = super().update(instance, validated_data)
        self.sync_sections(instance, keys)
        return instance

    class Meta:
        model = Promotion
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]


class SiteImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteImage
        fields = "__all__"
        read_only_fields = ["id", "updated_at"]


class SiteTextSerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteText
        fields = "__all__"
        read_only_fields = ["id", "updated_at"]


class AnalyticsEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnalyticsEvent
        fields = ["event_type", "section", "target", "session_id", "source", "device", "path", "event_id", "promotion_id"]
        extra_kwargs = {"event_id": {"validators": []}}

    def validate_session_id(self, value):
        if not value or len(value) > 64:
            raise serializers.ValidationError("Sesión inválida.")
        return value


class StoreCollectionSerializer(serializers.ModelSerializer):
    promotion_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), max_length=100, allow_empty=True)

    class Meta:
        model = StoreCollection
        fields = "__all__"
        read_only_fields = ["id", "key", "updated_at"]

    def validate_promotion_ids(self, ids):
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("No puedes repetir tratamientos en una sección.")
        if Promotion.objects.filter(id__in=ids).count() != len(ids):
            raise serializers.ValidationError("Un tratamiento ya no existe. Actualiza el catálogo.")
        return ids

    def to_representation(self, instance):
        data = super().to_representation(instance)
        existing = set(Promotion.objects.filter(id__in=data["promotion_ids"]).values_list("id", flat=True))
        data["promotion_ids"] = [pk for pk in data["promotion_ids"] if pk in existing]
        return data


class StoreSessionSerializer(serializers.ModelSerializer):
    session_id = serializers.RegexField(r"^[a-zA-Z0-9._-]{1,64}$")
    visitor_id = serializers.RegexField(r"^[a-zA-Z0-9._-]{1,64}$")
    cart_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), max_length=10, allow_empty=True)

    class Meta:
        model = StoreSession
        fields = ["session_id", "visitor_id", "cart_ids", "active"]
