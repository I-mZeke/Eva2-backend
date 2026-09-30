"""Permisos por rol (RBAC)."""
from rest_framework.permissions import BasePermission, SAFE_METHODS
from .models import Perfil

def es_admin_flota(user):
    if not user or not user.is_authenticated:
        return False
    perfil = getattr(user, 'perfil', None)
    return user.is_staff or (perfil is not None and perfil.rol == Perfil.Rol.ADMIN_FLOTA)

def rol_de(user):
    return 'ADMIN_FLOTA' if es_admin_flota(user) else 'PASAJERO'

class EsAdminFlota(BasePermission):
    def has_permission(self, request, view):
        return es_admin_flota(request.user)

class LecturaPublicaEscrituraAdmin(BasePermission):
    """GET público (catálogo); POST/PUT/PATCH/DELETE solo Administrador de Flota."""
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS or es_admin_flota(request.user)