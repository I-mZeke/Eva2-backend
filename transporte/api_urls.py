"""Rutas de la API. Incluye JWT, CRUD por router y Swagger protegido solo para administradores."""
from django.shortcuts import render, redirect
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.authentication import SessionAuthentication
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from . import views as v
from .permissions import EsAdminFlota, es_admin_flota

# Bloque: router con el CRUD de cada entidad
router = DefaultRouter()
router.register('ciudades', v.CiudadViewSet)
router.register('terminales', v.TerminalViewSet)
router.register('rutas', v.RutaViewSet)
router.register('buses', v.BusViewSet)
router.register('asientos', v.AsientoViewSet)
router.register('tarifas', v.TarifaViewSet)
router.register('servicios', v.ServicioViewSet)
router.register('servicio-asientos', v.ServicioAsientoViewSet)
router.register('pasajeros', v.PasajeroViewSet)
router.register('perfiles', v.PerfilViewSet)
router.register('carro-pasajes', v.CarroViewSet, basename='carro-pasajes')
router.register('ventas', v.VentaViewSet, basename='ventas')
router.register('mis-boletos', v.BoletoViewSet, basename='mis-boletos')


def docs_protegido(request):
    """Swagger solo para admin: visitante -> login, pasajero -> página 403 con template."""
    if not request.user.is_authenticated:
        return redirect(f'/login/?next={request.path}')
    if not es_admin_flota(request.user):
        return render(request, '403.html', status=403)
    return SpectacularSwaggerView.as_view(url_name='schema')(request)


urlpatterns = [
    path('token/', v.TokenConRolView.as_view(), name='token'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('registro/', v.RegistroAPIView.as_view(), name='api_registro'),

    # Esquema OpenAPI: solo admin con sesión (Swagger lo pide con la cookie de sesión)
    path('schema/', SpectacularAPIView.as_view(
        authentication_classes=[SessionAuthentication],
        permission_classes=[EsAdminFlota]), name='schema'),

    # Swagger: vista propia que muestra login o 403 con template según quién entre
    path('docs/', docs_protegido, name='docs'),

    path('', include(router.urls)),
]