# Selfing/core/utils.py
import os
from django.conf import settings
from django.contrib.staticfiles import finders

def link_callback(uri, rel):
    """
    Convierte un URI de HTML (como /static/...) en una ruta de sistema
    de archivos que xhtml2pdf pueda encontrar en el servidor.
    """
    # Maneja URLs de archivos de medios (uploads)
    if uri.startswith(settings.MEDIA_URL):
        path = os.path.join(settings.MEDIA_ROOT, uri.replace(settings.MEDIA_URL, ""))
    # Maneja URLs de archivos estáticos (CSS, imágenes, etc.)
    elif uri.startswith(settings.STATIC_URL):
        path = finders.find(uri.replace(settings.STATIC_URL, ""))
    else:
        # Para otros casos, considera la ruta como relativa a la raíz del proyecto
        path = os.path.join(settings.BASE_DIR, uri)

    # Asegurarse de que el archivo realmente exista
    if not os.path.isfile(path):
        return None
    return path