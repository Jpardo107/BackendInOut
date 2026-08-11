from django.conf import settings
from django.db import models


class VivadentAccess(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="vivadent_access")
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Acceso Vivadent: {self.user.username}"


class Promotion(models.Model):
    STATUS_CHOICES = [("active", "Activa"), ("draft", "Borrador"), ("inactive", "Inactiva")]
    title = models.CharField(max_length=160)
    subtitle = models.CharField(max_length=180)
    price = models.CharField(max_length=80)
    description = models.TextField(max_length=800)
    image_url = models.URLField(max_length=1000, blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="active")
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "id"]


class SiteImage(models.Model):
    key = models.SlugField(max_length=100, unique=True)
    name = models.CharField(max_length=160)
    section = models.CharField(max_length=100)
    image_url = models.URLField(max_length=1000)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["section", "name"]


class SiteText(models.Model):
    section = models.SlugField(max_length=100)
    key = models.SlugField(max_length=100)
    value = models.TextField(max_length=3000)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["section", "key"], name="vivadent_unique_site_text")]
        ordering = ["section", "key"]


class AnalyticsEvent(models.Model):
    EVENT_CHOICES = [("page_view", "Visita"), ("section_view", "Sección visitada"), ("click", "Clic")]
    event_type = models.CharField(max_length=20, choices=EVENT_CHOICES, db_index=True)
    section = models.CharField(max_length=100, blank=True, db_index=True)
    target = models.CharField(max_length=100, blank=True, db_index=True)
    session_id = models.CharField(max_length=64, db_index=True)
    source = models.CharField(max_length=100, blank=True)
    device = models.CharField(max_length=20, blank=True)
    path = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["created_at", "event_type"]), models.Index(fields=["section", "created_at"])]
