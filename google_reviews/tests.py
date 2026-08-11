import io
import json
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse


class _GoogleResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


@override_settings(
    GOOGLE_PLACES_API_KEY="test-key",
    GOOGLE_PLACE_ID="test-place",
    GOOGLE_REVIEWS_CACHE_SECONDS=3600,
)
class GoogleReviewsViewTests(TestCase):
    def setUp(self):
        cache.clear()

    @patch("google_reviews.services.urlopen")
    def test_returns_normalized_public_reviews(self, mocked_urlopen):
        mocked_urlopen.return_value = _GoogleResponse(json.dumps({
            "displayName": {"text": "Vivadent"},
            "rating": 4.9,
            "userRatingCount": 120,
            "googleMapsUri": "https://maps.google.com/example",
            "reviews": [
                {
                    "authorAttribution": {"displayName": "Una estrella"},
                    "rating": 1,
                    "text": {"text": "Reseña negativa"},
                },
                {
                    "authorAttribution": {"displayName": "Cuatro estrellas"},
                    "rating": 4,
                    "text": {"text": "Buena atención"},
                },
                {
                    "authorAttribution": {"displayName": "Ana", "photoUri": "https://example.com/ana.jpg"},
                    "rating": 5,
                    "text": {"text": "Excelente atención"},
                    "relativePublishTimeDescription": "Hace un mes",
                },
            ],
        }).encode())

        response = self.client.get(reverse("google_reviews:list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["rating"], 4.9)
        reviews = response.json()["reviews"]
        self.assertEqual([review["rating"] for review in reviews], [4, 5])
        self.assertEqual([review["author_name"] for review in reviews], ["Cuatro estrellas", "Ana"])
        request = mocked_urlopen.call_args.args[0]
        self.assertNotIn("test-key", request.full_url)
        self.assertEqual(request.headers["X-goog-api-key"], "test-key")

    @override_settings(GOOGLE_PLACES_API_KEY="", GOOGLE_PLACE_ID="")
    def test_returns_503_when_credentials_are_missing(self):
        response = self.client.get(reverse("google_reviews:list"))
        self.assertEqual(response.status_code, 503)
