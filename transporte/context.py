from .permissions import es_admin_flota
def rol_usuario(request):
    # Disponible en todos los templates como {{ es_admin }}
    return {'es_admin': es_admin_flota(request.user)}