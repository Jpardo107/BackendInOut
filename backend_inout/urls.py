from django.contrib import admin
from django.urls import path, include
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from user.views import CustomTokenObtainPairView
from user.api import user_info
from drf_yasg.generators import OpenAPISchemaGenerator


class CustomSchemaGenerator(OpenAPISchemaGenerator):
    def get_schema(self, request=None, public=False):
        schema = super().get_schema(request, public)
        schema.security = [{"Bearer": []}]
        return schema


schema_view = get_schema_view(
    openapi.Info(
        title="InOut API",
        default_version='v1',
        description="Documentación de la API del sistema InOut",
        terms_of_service="https://www.google.com/policies/terms/",
        contact=openapi.Contact(email="contacto@inout.cl"),
        license=openapi.License(name="BSD License"),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
    authentication_classes=[JWTAuthentication],
    generator_class=CustomSchemaGenerator,
)

urlpatterns = [
    path('admin/', admin.site.urls),

    # JWT Authentication
    path('api/token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    # Swagger y Redoc
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    path('api/userinfo/', user_info, name='user_info'),

    # Endpoints
    path('api/cargo-fijo/', include('cargo_fijo.urls')),
    path('api/documentacion/', include('documentacion.urls')),
    path('api/supervision/', include('supervision.urls')),
    path('', include('instalacion.urls')),
    path('api/', include('user.urls')),
]
