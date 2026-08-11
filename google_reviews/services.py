import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured


GOOGLE_REVIEWS_CACHE_KEY = "google-reviews:v2"
GOOGLE_REVIEWS_MIN_RATING = 4
GOOGLE_PLACES_FIELDS = (
    "displayName,rating,userRatingCount,reviews,googleMapsUri"
)


class GooglePlacesError(Exception):
    """Error controlado al consultar Google Places."""


def _normalized_review(review):
    author = review.get("authorAttribution") or {}
    text = review.get("text") or review.get("originalText") or {}
    return {
        "author_name": author.get("displayName", "Usuario de Google"),
        "author_photo_url": author.get("photoUri"),
        "author_url": author.get("uri"),
        "rating": review.get("rating"),
        "text": text.get("text", ""),
        "relative_time_description": review.get("relativePublishTimeDescription", ""),
        "publish_time": review.get("publishTime"),
        "google_maps_url": review.get("googleMapsUri"),
    }


def _is_positive_review(review):
    rating = review.get("rating")
    return isinstance(rating, (int, float)) and rating >= GOOGLE_REVIEWS_MIN_RATING


def get_google_reviews():
    cached = cache.get(GOOGLE_REVIEWS_CACHE_KEY)
    if cached is not None:
        return cached

    api_key = settings.GOOGLE_PLACES_API_KEY
    place_id = settings.GOOGLE_PLACE_ID
    if not api_key or not place_id:
        raise ImproperlyConfigured(
            "Configura GOOGLE_PLACES_API_KEY y GOOGLE_PLACE_ID en el backend."
        )

    url = f"https://places.googleapis.com/v1/places/{quote(place_id, safe='')}?languageCode=es"
    request = Request(
        url,
        headers={
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": GOOGLE_PLACES_FIELDS,
        },
    )

    try:
        with urlopen(request, timeout=8) as response:
            place = json.load(response)
    except HTTPError as error:
        detail = ""
        try:
            detail = json.loads(error.read()).get("error", {}).get("message", "")
        except (ValueError, AttributeError):
            pass
        raise GooglePlacesError(detail or f"Google Places respondió HTTP {error.code}.") from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise GooglePlacesError("No fue posible conectar con Google Places.") from error

    payload = {
        "place_name": (place.get("displayName") or {}).get("text", "Vivadent"),
        "rating": place.get("rating"),
        "user_rating_count": place.get("userRatingCount", 0),
        "google_maps_url": place.get("googleMapsUri"),
        "reviews": [
            _normalized_review(review)
            for review in place.get("reviews", [])
            if _is_positive_review(review)
        ],
    }
    cache.set(GOOGLE_REVIEWS_CACHE_KEY, payload, settings.GOOGLE_REVIEWS_CACHE_SECONDS)
    return payload
