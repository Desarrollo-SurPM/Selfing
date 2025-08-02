from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
]

# --- AQUÍ ESTÁ LA CORRECCIÓN ---
if settings.DEBUG:
    # Esta línea sirve los archivos de medios (PDFs, etc.). ¡La tienes bien!
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    
    # 👇 AÑADE ESTA LÍNEA QUE FALTA para servir los archivos estáticos (CSS, JS) 👇
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
