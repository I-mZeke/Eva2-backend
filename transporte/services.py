"""Lógica de negocio: carro, checkout y transiciones de estado con control de stock."""
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException
from .models import (Carro, ItemCarro, Pasajero, ServicioAsiento, TarifaServicio,
                     Venta, DetalleVenta, Boleto)

class ErrorNegocio(APIException):
    """Se traduce a HTTP 400 en la API; en la web se captura y se muestra como mensaje."""
    status_code = 400
    default_detail = 'Error de negocio.'

# Transiciones permitidas: PENDIENTE -> PAGADO -> ENTREGADO (o CANCELADO)
E = Venta.Estado
TRANSICIONES = {E.PENDIENTE: {E.PAGADO, E.CANCELADO}, E.PAGADO: {E.ENTREGADO, E.CANCELADO},
                E.ENTREGADO: set(), E.CANCELADO: set()}

def precio_de(sa):
    t = TarifaServicio.objects.filter(servicio_id=sa.servicio_id, tipo_asiento=sa.asiento.tipo).first()
    return t.precio if t else None

def _validar_disponible(sa):
    if sa.estado != ServicioAsiento.Estado.DISPONIBLE:
        raise ErrorNegocio(f'El asiento {sa.asiento.numero} ya no está disponible.')
    if not sa.servicio.activo or sa.servicio.fecha_salida <= timezone.now():
        raise ErrorNegocio('El servicio no está disponible para la venta.')

def agregar_item(usuario, servicio_asiento_id, nombre, documento):
    """Agrega al carro SIN descontar stock. Rechaza duplicados."""
    carro, _ = Carro.objects.get_or_create(usuario=usuario)
    sa = ServicioAsiento.objects.select_related('servicio', 'asiento').filter(pk=servicio_asiento_id).first()
    if not sa:
        raise ErrorNegocio('El asiento no existe.')
    _validar_disponible(sa)
    pasajero, _ = Pasajero.objects.update_or_create(documento=documento, defaults={'nombre': nombre})
    item, creado = ItemCarro.objects.get_or_create(carro=carro, servicio_asiento=sa,
                                                   defaults={'pasajero': pasajero})
    if not creado:
        raise ErrorNegocio('Ese asiento ya está en tu carro.')
    return item

def resumen_carro(usuario):
    carro, _ = Carro.objects.get_or_create(usuario=usuario)
    items = list(carro.items.select_related(
        'pasajero', 'servicio_asiento__asiento',
        'servicio_asiento__servicio__ruta__origen__ciudad',
        'servicio_asiento__servicio__ruta__destino__ciudad'))
    total = 0
    for i in items:
        i.precio = precio_de(i.servicio_asiento) or 0
        total += i.precio
    return carro, items, total

def checkout(usuario):
    """Carro -> Venta PENDIENTE con precios congelados. Vacía el carro. NO toca el stock."""
    Carro.objects.get_or_create(usuario=usuario)
    with transaction.atomic():
        carro = Carro.objects.select_for_update().get(usuario=usuario)
        items = list(carro.items.select_related('servicio_asiento__asiento',
                                                'servicio_asiento__servicio', 'pasajero'))
        if not items:
            raise ErrorNegocio('Tu carro está vacío.')
        venta = Venta.objects.create(usuario=usuario)
        for i in items:
            sa = i.servicio_asiento
            _validar_disponible(sa)
            precio = precio_de(sa)
            if precio is None:
                raise ErrorNegocio(f'Asiento {sa.asiento.numero} sin tarifa definida.')
            DetalleVenta.objects.create(venta=venta, servicio_asiento=sa,
                                        pasajero=i.pasajero, precio_unitario=precio)
        carro.items.all().delete()
        return venta

def cambiar_estado(venta_id, nuevo):
    """Único punto donde cambia el stock. Todo ocurre dentro de UNA transacción atómica:
    si algo falla, se revierte completo. select_for_update bloquea filas (evita doble venta)."""
    if nuevo not in Venta.Estado.values:
        raise ErrorNegocio('Estado inválido.')
    with transaction.atomic():
        venta = Venta.objects.select_for_update().get(pk=venta_id)
        if nuevo not in TRANSICIONES[venta.estado]:
            raise ErrorNegocio(f'No se puede pasar de {venta.estado} a {nuevo}.')
        ids = venta.detalles.values_list('servicio_asiento_id', flat=True)
        asientos = list(ServicioAsiento.objects.select_related('servicio')
                        .select_for_update(of=('self',)).filter(id__in=ids))
        ahora = timezone.now()

        if nuevo == E.PAGADO:
            # Stock insuficiente -> se rechaza toda la transacción
            if any(a.estado != ServicioAsiento.Estado.DISPONIBLE for a in asientos):
                raise ErrorNegocio('Stock insuficiente: algún asiento ya fue vendido.')
            if any(a.servicio.fecha_salida <= ahora for a in asientos):
                raise ErrorNegocio('Un servicio de la orden ya partió.')
            ServicioAsiento.objects.filter(id__in=[a.id for a in asientos]).update(
                estado=ServicioAsiento.Estado.OCUPADO)                  # descuento de stock
            for d in venta.detalles.all():
                Boleto.objects.create(detalle=d)                        # emite boletos UUID
            venta.pagada_en = ahora

        elif nuevo == E.CANCELADO and venta.estado == E.PAGADO:
            if any(a.servicio.fecha_salida <= ahora for a in asientos):
                raise ErrorNegocio('No se puede cancelar: el bus ya salió.')
            ServicioAsiento.objects.filter(id__in=[a.id for a in asientos]).update(
                estado=ServicioAsiento.Estado.DISPONIBLE)               # repone stock
            Boleto.objects.filter(detalle__venta=venta).update(anulado=True)

        venta.estado = nuevo
        venta.save()
        return venta