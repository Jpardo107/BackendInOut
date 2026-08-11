from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from .views import AnalyticsDashboardView, PromotionViewSet, PublicContentView, SiteImageViewSet, SiteTextViewSet, TrackEventView, VivadentTokenView, current_user

router = DefaultRouter()
router.register("promotions", PromotionViewSet, basename="vivadent-promotions")
router.register("images", SiteImageViewSet, basename="vivadent-images")
router.register("texts", SiteTextViewSet, basename="vivadent-texts")

urlpatterns = [
    path("auth/login/", VivadentTokenView.as_view(), name="vivadent-login"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="vivadent-refresh"),
    path("auth/me/", current_user, name="vivadent-me"),
    path("public/content/", PublicContentView.as_view(), name="vivadent-public-content"),
    path("public/events/", TrackEventView.as_view(), name="vivadent-track-event"),
    path("analytics/", AnalyticsDashboardView.as_view(), name="vivadent-analytics"),
    path("", include(router.urls)),
]
