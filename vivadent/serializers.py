from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import AnalyticsEvent, Promotion, SiteImage, SiteText


class VivadentTokenSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        access = getattr(self.user, "vivadent_access", None)
        if not access or not access.active:
            raise serializers.ValidationError("Este usuario no tiene acceso a Vivadent.")
        data["user"] = {"id": self.user.id, "username": self.user.username, "name": f"{self.user.nombres} {self.user.apellidos}".strip(), "email": self.user.email}
        return data


class PromotionSerializer(serializers.ModelSerializer):
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
        fields = ["event_type", "section", "target", "session_id", "source", "device", "path"]

    def validate_session_id(self, value):
        if not value or len(value) > 64:
            raise serializers.ValidationError("Sesión inválida.")
        return value
