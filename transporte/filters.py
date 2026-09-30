"""django-filter: búsqueda de servicios por origen, destino, fecha, rango de precio y tipo."""
import django_filters as df
from .models import Servicio, TipoAsiento

class ServicioFilter(df.FilterSet):
    origen = df.CharFilter(field_name='ruta__origen__ciudad__nombre', lookup_expr='icontains')
    destino = df.CharFilter(field_name='ruta__destino__ciudad__nombre', lookup_expr='icontains')
    fecha = df.DateFilter(field_name='fecha_salida', lookup_expr='date')
    precio_min = df.NumberFilter(field_name='tarifas__precio', lookup_expr='gte', distinct=True)
    precio_max = df.NumberFilter(field_name='tarifas__precio', lookup_expr='lte', distinct=True)
    tipo_asiento = df.ChoiceFilter(field_name='tarifas__tipo_asiento',
                                   choices=TipoAsiento.choices, distinct=True)
    class Meta:
        model = Servicio
        fields = []