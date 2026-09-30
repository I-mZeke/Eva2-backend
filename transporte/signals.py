"""Señales: automatizan la creación de Perfil/Carro y de los asientos de cada servicio."""
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Perfil, Carro, Servicio, ServicioAsiento

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def crear_perfil_y_carro(sender, instance, created, **kwargs):
    # Al crear un usuario: staff/superuser -> ADMIN_FLOTA, resto -> PASAJERO, y su carro 1:1
    if created:
        rol = Perfil.Rol.ADMIN_FLOTA if instance.is_staff else Perfil.Rol.PASAJERO
        Perfil.objects.create(usuario=instance, rol=rol)
        Carro.objects.create(usuario=instance)

@receiver(post_save, sender=Servicio)
def generar_asientos_servicio(sender, instance, created, **kwargs):
    # Al crear un servicio se copian los asientos físicos del bus como DISPONIBLES
    if created:
        ServicioAsiento.objects.bulk_create(
            [ServicioAsiento(servicio=instance, asiento=a) for a in instance.bus.asientos.all()])