from django.core.management.base import BaseCommand
from core.services.email_parser import GPSAlertParser

class Command(BaseCommand):
    help = 'Se conecta por IMAP, lee los correos de alertas GPS y genera los incidentes en BD.'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING('Iniciando conexión IMAP y lectura de correos...'))
        
        parser = GPSAlertParser()
        nuevos_incidentes = parser.process_unread_emails()
        
        if nuevos_incidentes > 0:
            self.stdout.write(self.style.SUCCESS(f'¡Éxito! Se generaron {nuevos_incidentes} nuevas alertas GPS.'))
        else:
            self.stdout.write(self.style.NOTICE('No se encontraron nuevos correos de alerta válidos.'))