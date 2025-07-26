import time
from django.core.management.base import BaseCommand
from pythonping import ping
from core.models import MonitoredService, ServiceStatusLog

class Command(BaseCommand):
    help = 'Realiza un ping a todos los servicios activos y registra su estado.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Iniciando chequeo de servicios...'))

        # Obtenemos solo los servicios que están marcados como activos
        active_services = MonitoredService.objects.filter(is_active=True)

        if not active_services:
            self.stdout.write(self.style.WARNING('No hay servicios activos para monitorear.'))
            return

        for service in active_services:
            self.stdout.write(f'Haciendo ping a: {service.name} ({service.ip_address})...')
            
            try:
                # Realizamos el ping con un timeout de 2 segundos
                response = ping(service.ip_address, count=1, timeout=2)
                
                is_up = response.success()
                avg_rtt = response.rtt_avg_ms if is_up else None

                if is_up:
                    self.stdout.write(self.style.SUCCESS(f' -> Éxito! Tiempo de respuesta: {avg_rtt:.2f} ms'))
                else:
                    self.stdout.write(self.style.ERROR(' -> Falló! El servicio está caído.'))

                # Guardamos el resultado en la base de datos
                ServiceStatusLog.objects.create(
                    service=service,
                    is_up=is_up,
                    response_time=avg_rtt
                )

            except Exception as e:
                # Capturamos cualquier otro error (ej: no se puede resolver el dominio)
                self.stdout.write(self.style.ERROR(f' -> Error al hacer ping: {e}'))
                ServiceStatusLog.objects.create(
                    service=service,
                    is_up=False,
                    response_time=None
                )
            
            # Pequeña pausa para no saturar la red
            time.sleep(1)

        self.stdout.write(self.style.SUCCESS('Chequeo de servicios finalizado.'))