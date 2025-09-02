import time
import subprocess
import platform
from django.core.management.base import BaseCommand
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
                # Usamos el comando ping del sistema operativo con reintentos
                system = platform.system().lower()
                is_up = False
                avg_rtt = None
                
                # Intentamos hasta 3 veces para evitar falsos negativos
                for attempt in range(3):
                    if system == "windows":
                        cmd = ["ping", "-n", "1", "-w", "5000", service.ip_address]
                    else:  # Linux, macOS, etc.
                        cmd = ["ping", "-c", "1", "-W", "5000", service.ip_address]
                    
                    try:
                        result = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
                        if result.returncode == 0:
                            is_up = True
                            # Intentar extraer el tiempo de respuesta del output
                            if result.stdout and "time=" in result.stdout:
                                try:
                                    time_part = result.stdout.split("time=")[1].split()[0]
                                    avg_rtt = float(time_part.replace("ms", ""))
                                except (IndexError, ValueError):
                                    pass
                            break  # Si fue exitoso, salir del loop
                        else:
                            # Si falló, esperar un poco antes del siguiente intento
                            if attempt < 2:  # No esperar en el último intento
                                time.sleep(1)
                    except subprocess.TimeoutExpired:
                        if attempt < 2:
                            time.sleep(1)
                        continue
                


                if is_up:
                    if avg_rtt:
                        self.stdout.write(self.style.SUCCESS(f' -> Éxito! Tiempo de respuesta: {avg_rtt:.2f} ms'))
                    else:
                        self.stdout.write(self.style.SUCCESS(' -> Éxito! Servicio disponible'))
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