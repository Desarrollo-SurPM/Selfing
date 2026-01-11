from django.contrib import admin
from django.urls import path, include, re_path # <--- Agregamos re_path
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve # <--- Importante para servir archivos del volumen

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    # --- BLOQUE CRÍTICO PARA RAILWAY VOLUMES ---
    # Esto permite que Django sirva las imágenes desde el disco persistente (/app/media)
    # Funciona aunque DEBUG sea False.
    re_path(r'^media/(?P<path>.*)$', serve, {
        'document_root': settings.MEDIA_ROOT,
    }),
]

# Configuración para archivos estáticos (CSS/JS)
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)