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

def start():
    """
    Inicia el planificador de tareas y añade el job de chequeo.
    """
    scheduler = BackgroundScheduler()
    # Añade la tarea para que se ejecute cada 10 minutos
    scheduler.add_job(check_services_job, 'interval', seconds=10)
    scheduler.start()
    print("Planificador de tareas iniciado. El chequeo de servicios se ejecutará cada 10 minutos.")