from django.apps import apps
from django.contrib import admin
# Registra automáticamente todos los modelos de la app en /admin
for m in apps.get_app_config('transporte').get_models():
    admin.site.register(m)