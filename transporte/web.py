"""Vistas HTML. Todas usan template. Los CRUD del panel se generan con una fábrica (crud_urls)."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import PermissionDenied
from django.db.models import ProtectedError
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import path, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import (ListView, DetailView, CreateView, UpdateView, DeleteView)
from . import services
from .filters import ServicioFilter
from .models import *
from .permissions import es_admin_flota
from .services import ErrorNegocio
from django.db import transaction

# ---------- 404 (usado por re_path comodín y por handler404) ----------
def pagina_no_encontrada(request, exception=None):
    if request.path.startswith('/api/'):     # las rutas de API responden JSON
        return JsonResponse({'detail': 'Ruta no encontrada.'}, status=404)
    return render(request, '404.html', status=404)

# ---------- Portal público / pasajero ----------
def home(request):
    base = (Servicio.objects.filter(activo=True, fecha_salida__gte=timezone.now())
            .select_related('ruta__origen__ciudad', 'ruta__destino__ciudad', 'bus')
            .prefetch_related('tarifas').order_by('fecha_salida'))
    filtro = ServicioFilter(request.GET or None, queryset=base)
    return render(request, 'home.html', {'servicios': filtro.qs.distinct()[:50]})

def servicio_detalle(request, pk):
    """Mapa de asientos: calcula la posición (columna/fila) de cada asiento en el bus."""
    servicio = get_object_or_404(
        Servicio.objects.select_related('ruta__origen__ciudad', 'ruta__destino__ciudad', 'bus'), pk=pk)
    tarifas = {t.tipo_asiento: t.precio for t in servicio.tarifas.all()}
    asientos = list(servicio.asientos.select_related('asiento').order_by('asiento__numero'))
    # Fila visual según numero % 4: 3 arriba, 4, (pasillo), 2, 1 abajo
    FILA = {3: 1, 0: 2, 2: 4, 1: 5}
    for a in asientos:
        n = a.asiento.numero
        a.precio = tarifas.get(a.asiento.tipo)
        a.col = (n - 1) // 4 + 1
        a.fila = FILA[n % 4]
    return render(request, 'servicio_detalle.html', {
        'servicio': servicio, 'asientos': asientos,
        'desde': min(tarifas.values()) if tarifas else None,
        'columnas': max((a.col for a in asientos), default=1)})


@login_required
@require_POST
def carro_agregar_varios(request):
    """Agrega varios asientos de una vez. Es todo o nada: si uno falla, no se agrega ninguno."""
    ids = request.POST.getlist('asientos')
    if not ids:
        messages.error(request, 'Selecciona al menos un asiento.')
        return redirect(request.META.get('HTTP_REFERER', 'home'))
    try:
        with transaction.atomic():
            for i in ids:
                services.agregar_item(request.user, int(i),
                                      request.POST[f'nombre_{i}'], request.POST[f'documento_{i}'])
        messages.success(request, f'{len(ids)} asiento(s) agregados al carro.')
        return redirect('carro')
    except ErrorNegocio as e:
        messages.error(request, e.detail)
        return redirect(request.META.get('HTTP_REFERER', 'home'))
    
class RegistroView(CreateView):
    form_class = UserCreationForm; template_name = 'registro.html'
    success_url = reverse_lazy('login')

@login_required
def carro(request):
    _, items, total = services.resumen_carro(request.user)
    return render(request, 'carro.html', {'items': items, 'total': total})

@login_required
@require_POST
def carro_agregar(request):
    try:
        services.agregar_item(request.user, int(request.POST['servicio_asiento']),
                              request.POST['nombre_pasajero'], request.POST['documento_pasajero'])
        messages.success(request, 'Asiento agregado al carro.')
    except ErrorNegocio as e:
        messages.error(request, e.detail)
    return redirect(request.META.get('HTTP_REFERER', 'carro'))

@login_required
@require_POST
def carro_quitar(request, pk):
    ItemCarro.objects.filter(pk=pk, carro__usuario=request.user).delete()
    return redirect('carro')

@login_required
@require_POST
def carro_checkout(request):
    try:
        venta = services.checkout(request.user)
        messages.success(request, f'Venta #{venta.pk} creada. Ahora puedes pagarla.')
        return redirect('ventas')
    except ErrorNegocio as e:
        messages.error(request, e.detail)
        return redirect('carro')

@login_required
def ventas(request):
    qs = Venta.objects.prefetch_related('detalles__servicio_asiento__asiento',
                                        'detalles__servicio_asiento__servicio', 'detalles__pasajero').order_by('-id')
    if not es_admin_flota(request.user):
        qs = qs.filter(usuario=request.user)
    return render(request, 'ventas.html', {'ventas': qs})

@login_required
@require_POST
def venta_estado(request, pk, estado):
    venta = get_object_or_404(Venta, pk=pk)
    if not es_admin_flota(request.user) and (venta.usuario != request.user or estado != Venta.Estado.PAGADO):
        raise PermissionDenied
    try:
        services.cambiar_estado(venta.pk, estado)
        messages.success(request, f'Venta #{pk} ahora está {estado}.')
    except ErrorNegocio as e:
        messages.error(request, e.detail)
    return redirect('ventas')

@login_required
def mis_boletos(request):
    boletos = (Boleto.objects.filter(detalle__venta__usuario=request.user, anulado=False)
               .select_related('detalle__servicio_asiento__asiento', 'detalle__servicio_asiento__servicio__ruta__origen__ciudad',
                               'detalle__servicio_asiento__servicio__ruta__destino__ciudad', 'detalle__pasajero'))
    return render(request, 'mis_boletos.html', {'boletos': boletos})

# ---------- Panel del administrador ----------
class PanelMixin(LoginRequiredMixin, UserPassesTestMixin):
    titulo = ''; slug = ''
    def test_func(self): return es_admin_flota(self.request.user)
    def get_context_data(self, **kw):
        c = super().get_context_data(**kw); c.update(titulo=self.titulo, slug=self.slug); return c

@login_required
def panel(request):
    if not es_admin_flota(request.user):
        raise PermissionDenied
    return render(request, 'panel.html')

def _valor(obj, campo):
    """Muestra el texto legible de un CHOICES si existe (get_X_display)."""
    f = getattr(obj, f'get_{campo}_display', None)
    return f() if f else getattr(obj, campo)

def crud_urls(modelo, campos, nombre_url, plural, formulario=None):
    """Fábrica: genera Lista, Detalle, Crear, Editar y Eliminar para un modelo y devuelve sus 5 rutas."""
    lista_url = reverse_lazy(f'{nombre_url}_lista')

    class Lista(PanelMixin, ListView):
        model = modelo; template_name = 'crud/lista.html'; paginate_by = 10
        ordering = ['pk']; slug = nombre_url; titulo = plural
        def get_context_data(self, **kw):
            c = super().get_context_data(**kw)
            c['encabezados'] = [modelo._meta.get_field(x).verbose_name for x in campos]
            c['filas'] = [(o, [_valor(o, x) for x in campos]) for o in c['object_list']]
            return c

    class Detalle(PanelMixin, DetailView):
        model = modelo; template_name = 'crud/detalle.html'; slug = nombre_url; titulo = plural
        def get_context_data(self, **kw):
            c = super().get_context_data(**kw)
            c['filas'] = [(f.verbose_name, _valor(self.object, f.name)) for f in modelo._meta.fields]
            return c

    class Crear(PanelMixin, SuccessMessageMixin, CreateView):
        model = modelo; template_name = 'crud/form.html'
        form_class = formulario                          # formulario propio (si existe)
        fields = None if formulario else '__all__'       # Django no admite ambos a la vez
        success_url = lista_url; success_message = 'Registro creado.'
        slug = nombre_url; titulo = plural

    class Editar(PanelMixin, SuccessMessageMixin, UpdateView):
        model = modelo; template_name = 'crud/form.html'
        form_class = formulario
        fields = None if formulario else '__all__'
        success_url = lista_url; success_message = 'Registro actualizado.'
        slug = nombre_url; titulo = plural
        
    class Eliminar(PanelMixin, DeleteView):
        model = modelo; template_name = 'crud/eliminar.html'
        success_url = lista_url; slug = nombre_url; titulo = plural
        def form_valid(self, form):
            try:
                messages.success(self.request, 'Registro eliminado.')
                return super().form_valid(form)
            except ProtectedError:      # FK PROTECT: tiene datos asociados
                messages.error(self.request, 'No se puede eliminar: tiene registros asociados.')
                return redirect(lista_url)

    p = f'panel/{nombre_url}/'
    return [path(p, Lista.as_view(), name=f'{nombre_url}_lista'),
            path(p + 'nuevo/', Crear.as_view(), name=f'{nombre_url}_crear'),
            path(p + '<int:pk>/', Detalle.as_view(), name=f'{nombre_url}_detalle'),
            path(p + '<int:pk>/editar/', Editar.as_view(), name=f'{nombre_url}_editar'),
            path(p + '<int:pk>/eliminar/', Eliminar.as_view(), name=f'{nombre_url}_eliminar')]