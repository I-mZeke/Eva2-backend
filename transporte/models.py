"""Modelos de BusExpress en 3FN. Ningún dato derivado se almacena (total, capacidad)."""
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

User = settings.AUTH_USER_MODEL


class TipoAsiento(models.TextChoices):          # CHOICES exigido por la pauta
    SEMICAMA = 'SEMICAMA', 'Semicama'
    CAMA = 'CAMA', 'Cama'


# ---------- Usuarios y roles ----------
class Perfil(models.Model):
    """1:1 con User. Guarda el rol que viaja como claim en el JWT."""
    class Rol(models.TextChoices):
        PASAJERO = 'PASAJERO', 'Pasajero'
        ADMIN_FLOTA = 'ADMIN_FLOTA', 'Administrador de Flota'
    usuario = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    rol = models.CharField(max_length=15, choices=Rol.choices, default=Rol.PASAJERO)
    def __str__(self): return f'{self.usuario} ({self.rol})'


# ---------- Geografía ----------
class Ciudad(models.Model):
    nombre = models.CharField(max_length=80, unique=True)
    region = models.CharField(max_length=80)
    def __str__(self): return self.nombre

class Terminal(models.Model):
    nombre = models.CharField(max_length=100)
    direccion = models.CharField(max_length=150)
    ciudad = models.ForeignKey(Ciudad, on_delete=models.PROTECT, related_name='terminales')
    def __str__(self): return f'{self.nombre} ({self.ciudad})'

class Ruta(models.Model):
    """Origen-Destino entre dos terminales."""
    origen = models.ForeignKey(Terminal, on_delete=models.PROTECT, related_name='rutas_origen')
    destino = models.ForeignKey(Terminal, on_delete=models.PROTECT, related_name='rutas_destino')
    duracion_minutos = models.PositiveIntegerField()
    class Meta:
        constraints = [models.UniqueConstraint(fields=['origen', 'destino'], name='uniq_ruta')]
    def clean(self):
        if self.origen_id and self.origen_id == self.destino_id:
            raise ValidationError('Origen y destino no pueden ser iguales.')
    def __str__(self): return f'{self.origen.ciudad} → {self.destino.ciudad}'


# ---------- Flota ----------
class Bus(models.Model):
    patente = models.CharField(max_length=10, unique=True)
    modelo = models.CharField(max_length=60)
    def __str__(self): return self.patente

class Asiento(models.Model):
    """Asiento físico del bus. El tipo (semicama/cama) es propiedad del asiento."""
    bus = models.ForeignKey(Bus, on_delete=models.CASCADE, related_name='asientos')
    numero = models.PositiveSmallIntegerField()
    tipo = models.CharField(max_length=10, choices=TipoAsiento.choices)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['bus', 'numero'], name='uniq_asiento_bus')]
    def __str__(self): return f'{self.bus} #{self.numero}'


# ---------- Servicios (itinerarios) ----------
class Servicio(models.Model):
    ruta = models.ForeignKey(Ruta, on_delete=models.PROTECT, related_name='servicios')
    bus = models.ForeignKey(Bus, on_delete=models.PROTECT, related_name='servicios')
    fecha_salida = models.DateTimeField()
    fecha_llegada = models.DateTimeField()
    activo = models.BooleanField(default=True)
    def clean(self):
        if self.fecha_salida and self.fecha_llegada and self.fecha_llegada <= self.fecha_salida:
            raise ValidationError('La llegada debe ser posterior a la salida.')
    def __str__(self): return f'{self.ruta} {self.fecha_salida:%d/%m/%Y %H:%M}'

class TarifaServicio(models.Model):
    """Precio por tipo de asiento en un servicio (evita repetir columnas de precio)."""
    servicio = models.ForeignKey(Servicio, on_delete=models.CASCADE, related_name='tarifas')
    tipo_asiento = models.CharField(max_length=10, choices=TipoAsiento.choices)
    precio = models.PositiveIntegerField()
    class Meta:
        constraints = [models.UniqueConstraint(fields=['servicio', 'tipo_asiento'], name='uniq_tarifa')]
    def __str__(self): return f'{self.servicio} - {self.tipo_asiento}: ${self.precio}'

class ServicioAsiento(models.Model):
    """'Stock' de la práctica: disponibilidad de cada asiento en cada servicio."""
    class Estado(models.TextChoices):
        DISPONIBLE = 'DISPONIBLE', 'Disponible'
        OCUPADO = 'OCUPADO', 'Ocupado'
    servicio = models.ForeignKey(Servicio, on_delete=models.CASCADE, related_name='asientos')
    asiento = models.ForeignKey(Asiento, on_delete=models.PROTECT, related_name='en_servicios')
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.DISPONIBLE)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['servicio', 'asiento'], name='uniq_servicio_asiento')]
    def __str__(self): return f'{self.servicio} asiento {self.asiento.numero}'


# ---------- Pasajero (3FN: documento -> nombre) ----------
class Pasajero(models.Model):
    documento = models.CharField(max_length=20, unique=True)   # RUT o pasaporte
    nombre = models.CharField(max_length=120)
    def __str__(self): return f'{self.nombre} ({self.documento})'


# ---------- Carro persistente (vive en PostgreSQL, ligado al usuario) ----------
class Carro(models.Model):
    usuario = models.OneToOneField(User, on_delete=models.CASCADE, related_name='carro')  # 1 a 1
    creado_en = models.DateTimeField(auto_now_add=True)
    def __str__(self): return f'Carro de {self.usuario}'

class ItemCarro(models.Model):
    carro = models.ForeignKey(Carro, on_delete=models.CASCADE, related_name='items')
    servicio_asiento = models.ForeignKey(ServicioAsiento, on_delete=models.CASCADE)
    pasajero = models.ForeignKey(Pasajero, on_delete=models.PROTECT)
    class Meta:   # Impide agregar dos veces el mismo asiento al carro
        constraints = [models.UniqueConstraint(fields=['carro', 'servicio_asiento'], name='uniq_item_carro')]


# ---------- Venta (orden histórica) ----------
class Venta(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = 'PENDIENTE', 'Pendiente'
        PAGADO = 'PAGADO', 'Pagado'
        ENTREGADO = 'ENTREGADO', 'Entregado'
        CANCELADO = 'CANCELADO', 'Cancelado'
    usuario = models.ForeignKey(User, on_delete=models.PROTECT, related_name='ventas')
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.PENDIENTE)
    creada_en = models.DateTimeField(auto_now_add=True)
    pagada_en = models.DateTimeField(null=True, blank=True)
    @property
    def total(self):   # Dato derivado: se calcula, no se almacena (3FN)
        return sum(d.precio_unitario for d in self.detalles.all())
    def __str__(self): return f'Venta #{self.pk} - {self.estado}'

class DetalleVenta(models.Model):
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name='detalles')
    servicio_asiento = models.ForeignKey(ServicioAsiento, on_delete=models.PROTECT, related_name='detalles')
    pasajero = models.ForeignKey(Pasajero, on_delete=models.PROTECT)
    precio_unitario = models.PositiveIntegerField()   # Precio congelado al momento de la compra
    class Meta:
        constraints = [models.UniqueConstraint(fields=['venta', 'servicio_asiento'], name='uniq_detalle')]

class Boleto(models.Model):
    """Se emite automáticamente al pasar a PAGADO. Código único UUID."""
    detalle = models.OneToOneField(DetalleVenta, on_delete=models.CASCADE, related_name='boleto')
    codigo = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    emitido_en = models.DateTimeField(auto_now_add=True)
    anulado = models.BooleanField(default=False)

# Alias a nivel de módulo: drf-spectacular los usa para nombrar los enums en Swagger
EstadoVenta = Venta.Estado
EstadoAsientoServicio = ServicioAsiento.Estado