"""Vistas API (DRF). Permisos: catálogo público, carro/compras autenticado, gestión solo admin."""
from django.contrib.auth import get_user_model
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets, mixins, generics
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from . import services
from .filters import ServicioFilter
from .models import *
from .permissions import EsAdminFlota, LecturaPublicaEscrituraAdmin, es_admin_flota
from .serializers import *

User = get_user_model()


class TokenConRolView(TokenObtainPairView):
    serializer_class = TokenConRolSerializer


class RegistroAPIView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegistroSerializer
    permission_classes = [AllowAny]


# ---- Catálogo: GET público, escritura solo admin ----
class CatalogoViewSet(viewsets.ModelViewSet):
    permission_classes = [LecturaPublicaEscrituraAdmin]


class CiudadViewSet(CatalogoViewSet):
    queryset = Ciudad.objects.order_by('id')
    serializer_class = CiudadSerializer
    search_fields = ['nombre']
    filterset_fields = ['region']


class TerminalViewSet(CatalogoViewSet):
    queryset = Terminal.objects.order_by('id')
    serializer_class = TerminalSerializer
    filterset_fields = ['ciudad']


class RutaViewSet(CatalogoViewSet):
    queryset = Ruta.objects.order_by('id')
    serializer_class = RutaSerializer
    filterset_fields = ['origen', 'destino']


class BusViewSet(CatalogoViewSet):
    queryset = Bus.objects.order_by('id')
    serializer_class = BusSerializer
    search_fields = ['patente', 'modelo']


class AsientoViewSet(CatalogoViewSet):
    queryset = Asiento.objects.order_by('id')
    serializer_class = AsientoSerializer
    filterset_fields = ['bus', 'tipo']


class TarifaViewSet(CatalogoViewSet):
    queryset = TarifaServicio.objects.order_by('id')
    serializer_class = TarifaSerializer
    filterset_fields = {'servicio': ['exact'], 'tipo_asiento': ['exact'], 'precio': ['gte', 'lte']}


class ServicioAsientoViewSet(CatalogoViewSet):
    queryset = ServicioAsiento.objects.order_by('id')
    serializer_class = ServicioAsientoSerializer
    filterset_fields = ['servicio', 'estado']


class PasajeroViewSet(viewsets.ModelViewSet):      # datos personales: solo admin
    queryset = Pasajero.objects.order_by('id')
    serializer_class = PasajeroSerializer
    permission_classes = [EsAdminFlota]
    search_fields = ['documento', 'nombre']


class PerfilViewSet(viewsets.ModelViewSet):
    queryset = Perfil.objects.order_by('id')
    serializer_class = PerfilSerializer
    permission_classes = [EsAdminFlota]
    filterset_fields = ['rol']


class ServicioViewSet(CatalogoViewSet):
    queryset = (Servicio.objects.select_related('ruta__origen__ciudad', 'ruta__destino__ciudad', 'bus')
                .prefetch_related('tarifas').order_by('fecha_salida'))
    serializer_class = ServicioSerializer
    filterset_class = ServicioFilter
    ordering_fields = ['fecha_salida']

    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def buscar(self, request):
        """GET /api/servicios/buscar/?origen=&destino=&fecha=&precio_max="""
        qs = self.filter_queryset(self.get_queryset().filter(activo=True, fecha_salida__gte=timezone.now()))
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    @extend_schema(responses=AsientoDisponibilidadSerializer(many=True))
    @action(detail=True, methods=['get'], permission_classes=[AllowAny])
    def asientos(self, request, pk=None):
        """GET /api/servicios/{id}/asientos/"""
        servicio = self.get_object()
        tarifas = {t.tipo_asiento: t.precio for t in servicio.tarifas.all()}
        qs = servicio.asientos.select_related('asiento').order_by('asiento__numero')
        return Response(AsientoDisponibilidadSerializer(qs, many=True, context={'tarifas': tarifas}).data)


# ---- Carro (solo usuario autenticado; siempre limitado a SU carro) ----
class CarroViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, mixins.DestroyModelMixin,
                   viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = ItemCarroSerializer
    filter_backends = []
    pagination_class = None

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):   # al generar Swagger no hay usuario real
            return ItemCarro.objects.none()
        return ItemCarro.objects.filter(carro__usuario=self.request.user)   # nunca ve carros ajenos

    def list(self, request):                       # GET /api/carro-pasajes/
        carro, items, total = services.resumen_carro(request.user)
        return Response({'items': ItemCarroSerializer(items, many=True).data, 'total': total})

    @extend_schema(request=AgregarItemSerializer, responses=ItemCarroSerializer)
    def create(self, request):                     # POST /api/carro-pasajes/
        s = AgregarItemSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        item = services.agregar_item(request.user, d['servicio_asiento'],
                                     d['nombre_pasajero'], d['documento_pasajero'])
        return Response(ItemCarroSerializer(item).data, status=201)

    @extend_schema(request=None, responses={204: None})
    @action(detail=False, methods=['delete'])      # DELETE /api/carro-pasajes/vaciar/
    def vaciar(self, request):
        self.get_queryset().delete()
        return Response(status=204)


# ---- Ventas ----
class VentaViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = VentaSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['estado']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):   # al generar Swagger no hay usuario real
            return Venta.objects.none()
        qs = Venta.objects.prefetch_related('detalles__servicio_asiento__asiento',
                                            'detalles__pasajero', 'detalles__boleto').order_by('-id')
        return qs if es_admin_flota(self.request.user) else qs.filter(usuario=self.request.user)

    @extend_schema(request=None, responses=VentaSerializer)
    @action(detail=False, methods=['post'])        # POST /api/ventas/checkout/
    def checkout(self, request):
        return Response(VentaSerializer(services.checkout(request.user)).data, status=201)

    @extend_schema(request=None, responses=VentaSerializer)
    @action(detail=True, methods=['post'])         # POST /api/ventas/{id}/pagar/
    def pagar(self, request, pk=None):
        venta = self.get_object()                  # get_queryset garantiza que sea suya
        return Response(VentaSerializer(services.cambiar_estado(venta.pk, Venta.Estado.PAGADO)).data)

    @extend_schema(request=EstadoSerializer, responses=VentaSerializer)
    @action(detail=True, methods=['patch'], permission_classes=[EsAdminFlota])
    def estado(self, request, pk=None):            # PATCH /api/ventas/{id}/estado/
        s = EstadoSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(VentaSerializer(services.cambiar_estado(pk, s.validated_data['estado'])).data)


class BoletoViewSet(viewsets.ReadOnlyModelViewSet):    # GET /api/mis-boletos/
    serializer_class = BoletoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):   # al generar Swagger no hay usuario real
            return Boleto.objects.none()
        return (Boleto.objects.filter(detalle__venta__usuario=self.request.user, anulado=False)
                .select_related('detalle__servicio_asiento__asiento', 'detalle__servicio_asiento__servicio',
                                'detalle__pasajero').order_by('-id'))