"""Formularios del panel: generan asientos al crear un bus y tarifas al crear un servicio."""
from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction
from .models import Bus, Asiento, Servicio, TarifaServicio, TipoAsiento


class BusForm(forms.ModelForm):
    # Campos que no son columnas de Bus: solo sirven para generar sus asientos
    total_asientos = forms.IntegerField(min_value=1, max_value=80, required=False,
                                        label='Cantidad total de asientos')
    asientos_cama = forms.IntegerField(min_value=0, required=False, initial=0,
                                       label='De ellos, cuántos son tipo Cama')

    class Meta:
        model = Bus
        fields = ['patente', 'modelo']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.asientos.exists():
            # Bus existente: los asientos no se regeneran (podrían estar en servicios)
            self.fields['total_asientos'].disabled = True
            self.fields['asientos_cama'].disabled = True
            self.fields['total_asientos'].initial = self.instance.asientos.count()
            self.fields['asientos_cama'].initial = self.instance.asientos.filter(tipo='CAMA').count()
            self.fields['total_asientos'].help_text = 'Para cambiar asientos usa el CRUD de Asientos.'

    def clean(self):
        d = super().clean()
        total, cama = d.get('total_asientos'), d.get('asientos_cama') or 0
        if not self.instance.pk and not total:
            raise ValidationError('Indica la cantidad total de asientos.')
        if total and cama > total:
            raise ValidationError('Los asientos Cama no pueden superar el total.')
        return d

    @transaction.atomic
    def save(self, commit=True):
        bus = super().save(commit)
        total = self.cleaned_data.get('total_asientos')
        cama = self.cleaned_data.get('asientos_cama') or 0
        if total and not bus.asientos.exists():
            # Bloque: genera los asientos 1..total; los últimos 'cama' son tipo CAMA
            Asiento.objects.bulk_create([
                Asiento(bus=bus, numero=n,
                        tipo=TipoAsiento.CAMA if n > total - cama else TipoAsiento.SEMICAMA)
                for n in range(1, total + 1)])
        return bus


class ServicioForm(forms.ModelForm):
    precio_semicama = forms.IntegerField(min_value=1, required=False, label='Precio Semicama ($)')
    precio_cama = forms.IntegerField(min_value=1, required=False, label='Precio Cama ($)')

    class Meta:
        model = Servicio
        fields = ['ruta', 'bus', 'fecha_salida', 'fecha_llegada', 'activo']
        widgets = {
            'fecha_salida': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'fecha_llegada': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in ('fecha_salida', 'fecha_llegada'):
            self.fields[f].input_formats = ['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M']
        if self.instance.pk:
            self.fields['bus'].disabled = True    # cambiar el bus dejaría asientos inconsistentes
            for t in self.instance.tarifas.all():
                self.fields[f'precio_{t.tipo_asiento.lower()}'].initial = t.precio

    def clean(self):
        d = super().clean()
        bus = d.get('bus')
        if bus:
            tipos = set(bus.asientos.values_list('tipo', flat=True))
            if not tipos:
                raise ValidationError('Ese bus no tiene asientos. Créalo con su cantidad de asientos.')
            for tipo in tipos:   # exige precio solo para los tipos que el bus realmente tiene
                if not d.get(f'precio_{tipo.lower()}'):
                    raise ValidationError(f'Falta el precio para asientos {tipo.title()}.')
        return d

    @transaction.atomic
    def save(self, commit=True):
        servicio = super().save(commit)   # la señal crea los ServicioAsiento al crear
        for tipo in TipoAsiento.values:
            precio = self.cleaned_data.get(f'precio_{tipo.lower()}')
            if precio and servicio.bus.asientos.filter(tipo=tipo).exists():
                TarifaServicio.objects.update_or_create(
                    servicio=servicio, tipo_asiento=tipo, defaults={'precio': precio})
        return servicio