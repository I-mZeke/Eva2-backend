"""Serializers de la API. Incluye JWT con claim de rol y validación de contraseña."""
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from . import services
from .models import *
from .permissions import rol_de

User = get_user_model()


# ---- JWT con claim de rol ----
class TokenConRolSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['rol'] = rol_de(user)          # claim personalizado dentro del payload
        token['username'] = user.username
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data['rol'] = rol_de(self.user)      # también en el cuerpo de la respuesta
        return data


class RegistroSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password']

    def validate_password(self, value):
        validate_password(value)             # aplica los validadores de settings.py
        return value

    def create(self, d):
        return User.objects.create_user(**d)   # la señal crea Perfil y Carro


# ---- CRUD simples ----
class CiudadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ciudad
        fields = '__all__'


class TerminalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Terminal
        fields = '__all__'


class RutaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ruta
        fields = '__all__'

    def validate(self, d):
        if d['origen'] == d['destino']:
            raise serializers.ValidationError('Origen y destino no pueden ser iguales.')
        return d


class BusSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bus
        fields = '__all__'


class AsientoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Asiento
        fields = '__all__'


class TarifaSerializer(serializers.ModelSerializer):
    class Meta:
        model = TarifaServicio
        fields = '__all__'


class ServicioAsientoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServicioAsiento
        fields = '__all__'


class PasajeroSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pasajero
        fields = '__all__'


class PerfilSerializer(serializers.ModelSerializer):
    class Meta:
        model = Perfil
        fields = '__all__'


class ServicioSerializer(serializers.ModelSerializer):
    ruta_texto = serializers.CharField(source='ruta.__str__', read_only=True)
    tarifas = TarifaSerializer(many=True, read_only=True)

    class Meta:
        model = Servicio
        fields = '__all__'


class AsientoDisponibilidadSerializer(serializers.ModelSerializer):
    """Vista pública de asientos de un servicio con su precio."""
    numero = serializers.IntegerField(source='asiento.numero', read_only=True)
    tipo = serializers.CharField(source='asiento.tipo', read_only=True)
    precio = serializers.SerializerMethodField()

    class Meta:
        model = ServicioAsiento
        fields = ['id', 'numero', 'tipo', 'estado', 'precio']

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_precio(self, obj):
        return self.context.get('tarifas', {}).get(obj.asiento.tipo)


# ---- Carro ----
class AgregarItemSerializer(serializers.Serializer):
    servicio_asiento = serializers.IntegerField()
    nombre_pasajero = serializers.CharField(max_length=120)
    documento_pasajero = serializers.CharField(max_length=20)


class ItemCarroSerializer(serializers.ModelSerializer):
    asiento_numero = serializers.IntegerField(source='servicio_asiento.asiento.numero', read_only=True)
    tipo = serializers.CharField(source='servicio_asiento.asiento.tipo', read_only=True)
    servicio = serializers.IntegerField(source='servicio_asiento.servicio_id', read_only=True)
    pasajero_nombre = serializers.CharField(source='pasajero.nombre', read_only=True)
    pasajero_documento = serializers.CharField(source='pasajero.documento', read_only=True)
    precio = serializers.SerializerMethodField()

    class Meta:
        model = ItemCarro
        fields = ['id', 'servicio_asiento', 'servicio', 'asiento_numero', 'tipo',
                  'pasajero_nombre', 'pasajero_documento', 'precio']

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_precio(self, obj):
        return services.precio_de(obj.servicio_asiento)


# ---- Ventas ----
class DetalleVentaSerializer(serializers.ModelSerializer):
    asiento = serializers.IntegerField(source='servicio_asiento.asiento.numero', read_only=True)
    pasajero = serializers.CharField(source='pasajero.nombre', read_only=True)
    codigo_boleto = serializers.SerializerMethodField()

    class Meta:
        model = DetalleVenta
        fields = ['id', 'asiento', 'pasajero', 'precio_unitario', 'codigo_boleto']

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_codigo_boleto(self, obj):
        b = getattr(obj, 'boleto', None)
        return str(b.codigo) if b else None


class VentaSerializer(serializers.ModelSerializer):
    detalles = DetalleVentaSerializer(many=True, read_only=True)
    total = serializers.IntegerField(read_only=True)

    class Meta:
        model = Venta
        fields = ['id', 'estado', 'creada_en', 'pagada_en', 'total', 'detalles']


class EstadoSerializer(serializers.Serializer):
    estado = serializers.ChoiceField(choices=Venta.Estado.choices)


class BoletoSerializer(serializers.ModelSerializer):
    asiento = serializers.IntegerField(source='detalle.servicio_asiento.asiento.numero')
    servicio = serializers.CharField(source='detalle.servicio_asiento.servicio.__str__')
    pasajero = serializers.CharField(source='detalle.pasajero.nombre')

    class Meta:
        model = Boleto
        fields = ['codigo', 'servicio', 'asiento', 'pasajero', 'emitido_en']