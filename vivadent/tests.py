from django.urls import reverse
from rest_framework.test import APITestCase

from user.models import Usuario
from .models import AnalyticsEvent, VivadentAccess


class VivadentApiTests(APITestCase):
    def setUp(self):
        self.user = Usuario.objects.create_user(username="vivadent-test", password="SafePass123!", nombres="Viva", apellidos="Dent", rut="99999999-9", email="test@vivadent.cl")
        VivadentAccess.objects.create(user=self.user)

    def login(self):
        response = self.client.post(reverse("vivadent-login"), {"username": "vivadent-test", "password": "SafePass123!"})
        self.assertEqual(response.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def test_vivadent_user_is_isolated_from_inout_api(self):
        self.login()
        response = self.client.get("/api/userinfo/")
        self.assertEqual(response.status_code, 401)

    def test_admin_can_crud_promotions(self):
        self.login()
        response = self.client.post("/api/vivadent/promotions/", {"title": "Promo", "subtitle": "Especial", "price": "$10.000", "description": "Descripción", "status": "active", "order": 10})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.client.patch(f"/api/vivadent/promotions/{response.data['id']}/", {"price": "$12.000"}).status_code, 200)
        self.assertEqual(self.client.delete(f"/api/vivadent/promotions/{response.data['id']}/").status_code, 204)

    def test_public_content_and_events_do_not_require_login(self):
        self.assertEqual(self.client.get("/api/vivadent/public/content/").status_code, 200)
        response = self.client.post("/api/vivadent/public/events/", {"event_type": "click", "section": "promociones", "target": "whatsapp", "session_id": "abc-123", "device": "mobile"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(AnalyticsEvent.objects.count(), 1)
