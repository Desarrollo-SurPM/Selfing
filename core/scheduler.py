from apscheduler.schedulers.background import BackgroundScheduler
from django.core.management import call_command

def check_services_job():
    """
    Función que ejecuta el comando de Django para chequear los servicios.
    """
    try:
        print("Scheduler: Ejecutando el chequeo de servicios...")
        call_command('check_services')
        print("Scheduler: Chequeo de servicios finalizado.")
    except Exception as e:
        print(f"Scheduler: Error al ejecutar check_services: {e}")

# 👇 NUEVA TAREA AUTOMÁTICA PARA EL GPS 👇
def fetch_gps_alerts_job():
    """
    Función que revisa el correo en busca de nuevas alarmas GPS de MITTA.
    """
    try:
        print("Scheduler: Buscando nuevos correos de alertas GPS...")
        call_command('fetch_gps_alerts')
    except Exception as e:
        print(f"Scheduler: Error al ejecutar fetch_gps_alerts: {e}")

def start():
    """
    Inicia el planificador de tareas y añade todos los jobs.
    """
    scheduler = BackgroundScheduler()
    
    # 1. Tarea de servicios (Cada 5 minutos)
    scheduler.add_job(check_services_job, 'interval', minutes=5)
    
    # 2. Tarea de GPS (Cada 30 segundos para respuesta casi en tiempo real)
    scheduler.add_job(fetch_gps_alerts_job, 'interval', seconds=30)
    
    scheduler.start()
    print("Planificador de tareas iniciado. Chequeo de servicios (5 min) y Radar GPS (30 seg) activos.")