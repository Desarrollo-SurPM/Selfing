import os
from django.apps import AppConfig

class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        # El planificador solo se inicia en el proceso principal del servidor.
        # La variable de entorno RUN_MAIN la pone el comando 'runserver'.
        if os.environ.get('RUN_MAIN', None) != 'true':
            from . import scheduler
            scheduler.start()