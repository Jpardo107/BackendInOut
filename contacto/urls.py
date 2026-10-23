from django.urls import path

from .views import cotizacion

urlpatterns = [
    path("cotizaciones/", cotizacion, name="public-cotizacion"),
]
