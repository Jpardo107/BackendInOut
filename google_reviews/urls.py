from django.urls import path

from .views import GoogleReviewsView


app_name = "google_reviews"

urlpatterns = [
    path("", GoogleReviewsView.as_view(), name="list"),
]
