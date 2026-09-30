from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from transporte.models import *

class Command(BaseCommand):
    help = 'Carga datos de ejemplo'
    def handle(self, *args, **kwargs):
        stgo, _ = Ciudad.objects.get_or_create(nombre='Santiago', defaults={'region': 'Metropolitana'})
        val, _ = Ciudad.objects.get_or_create(nombre='Valparaíso', defaults={'region': 'Valparaíso'})
        t1, _ = Terminal.objects.get_or_create(nombre='Terminal Alameda', defaults={'direccion': 'Alameda 3750', 'ciudad': stgo})
        t2, _ = Terminal.objects.get_or_create(nombre='Terminal Valparaíso', defaults={'direccion': 'Pedro Montt 2800', 'ciudad': val})
        ruta, _ = Ruta.objects.get_or_create(origen=t1, destino=t2, defaults={'duracion_minutos': 120})
        bus, creado = Bus.objects.get_or_create(patente='ABCD12', defaults={'modelo': 'Marcopolo G7'})
        if creado:   # 10 asientos: 1-6 semicama, 7-10 cama
            for n in range(1, 11):
                Asiento.objects.create(bus=bus, numero=n, tipo='SEMICAMA' if n <= 6 else 'CAMA')
        salida = timezone.now() + timedelta(days=2)
        serv = Servicio.objects.create(ruta=ruta, bus=bus, fecha_salida=salida,
                                       fecha_llegada=salida + timedelta(hours=2))  # la señal crea los ServicioAsiento
        TarifaServicio.objects.create(servicio=serv, tipo_asiento='SEMICAMA', precio=8000)
        TarifaServicio.objects.create(servicio=serv, tipo_asiento='CAMA', precio=15000)
        self.stdout.write(self.style.SUCCESS('Datos de ejemplo cargados.'))