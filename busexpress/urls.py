from django.contrib import admin
from django.urls import path, include, re_path
from transporte.web import pagina_no_encontrada

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('transporte.api_urls')),   # API + Swagger en /api/docs/
    path('', include('transporte.web_urls')),       # Web con templates
    # 404 comodín: DEBE IR ÚLTIMO. Captura cualquier ruta que no exista.
    re_path(r'^.*$', pagina_no_encontrada),
]
handler404 = 'transporte.web.pagina_no_encontrada'  # respaldo cuando DEBUG=False