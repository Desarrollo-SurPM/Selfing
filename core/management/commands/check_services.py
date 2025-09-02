import time
import requests
import urllib3
from urllib.parse import urlparse
from django.core.management.base import BaseCommand
from core.models import MonitoredService, ServiceStatusLog

# Deshabilitar advertencias SSL para evitar spam en logs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
                # Usamos HTTP requests en lugar de ping para mejor compatibilidad
                is_up = False
                response_time = None
                
                # Preparar la URL para la solicitud HTTP
                url = service.ip_address
                if not url.startswith(('http://', 'https://')):
                    url = f'https://{url}'
                
                # Intentamos hasta 3 veces para evitar falsos negativos
                for attempt in range(3):
                    try:
                        start_time = time.time()
                        response = requests.get(
                            url, 
                            timeout=8, 
                            verify=False,  # Ignorar certificados SSL inválidos
                            allow_redirects=True
                        )
                        end_time = time.time()
                        
                        # Consideramos exitoso cualquier respuesta HTTP (incluso errores 4xx/5xx)
                        # ya que indica que el servidor está respondiendo
                        if response.status_code < 600:
                            is_up = True
                            response_time = (end_time - start_time) * 1000  # Convertir a ms
                            break
                        else:
                            if attempt < 2:
                                time.sleep(1)
                                
                    except requests.exceptions.SSLError:
                        # Si falla HTTPS, intentar con HTTP
                        try:
                            http_url = url.replace('https://', 'http://')
                            start_time = time.time()
                            response = requests.get(http_url, timeout=8, allow_redirects=True)
                            end_time = time.time()
                            
                            if response.status_code < 600:
                                is_up = True
                                response_time = (end_time - start_time) * 1000
                                break
                        except:
                            pass
                        
                        if attempt < 2:
                            time.sleep(1)
                            
                    except (requests.exceptions.RequestException, requests.exceptions.Timeout):
                        if attempt < 2:
                            time.sleep(1)
                        continue

                if is_up:
                    if response_time:
                        self.stdout.write(self.style.SUCCESS(f' -> Éxito! Tiempo de respuesta: {response_time:.2f} ms'))
                    else:
                        self.stdout.write(self.style.SUCCESS(' -> Éxito! Servicio disponible'))
                else:
                    self.stdout.write(self.style.ERROR(' -> Falló! El servicio está caído.'))

                # Guardamos el resultado en la base de datos
                ServiceStatusLog.objects.create(
                    service=service,
                    is_up=is_up,
                    response_time=response_time
                )

            except Exception as e:
                # Capturamos cualquier otro error
                self.stdout.write(self.style.ERROR(f' -> Error al verificar servicio: {e}'))
                ServiceStatusLog.objects.create(
                    service=service,
                    is_up=False,
                    response_time=None
                )
            
            # Pequeña pausa para no saturar la red
            time.sleep(1)

        self.stdout.write(self.style.SUCCESS('Chequeo de servicios finalizado.'))