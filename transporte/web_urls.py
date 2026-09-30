from django.contrib.auth import views as auth_views
from django.urls import path
from . import web
from .models import *
from .forms import BusForm, ServicioForm

urlpatterns = [
    path('', web.home, name='home'),
    path('servicio/<int:pk>/', web.servicio_detalle, name='servicio_publico'),
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('registro/', web.RegistroView.as_view(), name='registro'),
    path('carro/', web.carro, name='carro'),
    path('carro/agregar/', web.carro_agregar, name='carro_agregar'),
    path('carro/quitar/<int:pk>/', web.carro_quitar, name='carro_quitar'),
    path('carro/checkout/', web.carro_checkout, name='carro_checkout'),
    path('ventas/', web.ventas, name='ventas'),
    path('ventas/<int:pk>/estado/<str:estado>/', web.venta_estado, name='venta_estado'),
    path('boletos/', web.mis_boletos, name='boletos'),
    path('panel/', web.panel, name='panel'),
    path('carro/agregar-varios/', web.carro_agregar_varios, name='carro_agregar_varios'),
]
# CRUD web de cada entidad maestra (5 vistas + templates cada una)
urlpatterns += web.crud_urls(Ciudad, ['nombre', 'region'], 'ciudad', 'Ciudades')
urlpatterns += web.crud_urls(Terminal, ['nombre', 'direccion', 'ciudad'], 'terminal', 'Terminales')
urlpatterns += web.crud_urls(Ruta, ['origen', 'destino', 'duracion_minutos'], 'ruta', 'Rutas')
urlpatterns += web.crud_urls(Bus, ['patente', 'modelo'], 'bus', 'Buses', formulario=BusForm)
urlpatterns += web.crud_urls(Asiento, ['bus', 'numero', 'tipo'], 'asiento', 'Asientos')
urlpatterns += web.crud_urls(Servicio, ['ruta', 'bus', 'fecha_salida', 'fecha_llegada', 'activo'], 'servicio', 'Servicios', formulario=ServicioForm)
urlpatterns += web.crud_urls(TarifaServicio, ['servicio', 'tipo_asiento', 'precio'], 'tarifa', 'Tarifas')
urlpatterns += web.crud_urls(ServicioAsiento, ['servicio', 'asiento', 'estado'], 'servasiento', 'Asientos por servicio')
urlpatterns += web.crud_urls(Pasajero, ['documento', 'nombre'], 'pasajero', 'Pasajeros')
urlpatterns += web.crud_urls(Perfil, ['usuario', 'rol'], 'perfil', 'Perfiles y roles')