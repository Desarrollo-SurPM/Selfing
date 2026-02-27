import datetime
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from core.models import (
    Company, Installation, OperatorProfile, ShiftType, OperatorShift,
    ChecklistItem, MonitoredService, Sector, GPSIncident, Vehicle, GPSNotificationSettings
)

class Command(BaseCommand):
    help = 'Puebla la base de datos con datos de prueba incluyendo jerarquía de Checklist'

    def handle(self, *args, **kwargs):
        self.stdout.write("Iniciando carga de datos semilla (Seed)...")

        # ==========================================
        # 1. CREACIÓN DE USUARIOS
        # ==========================================
        admin_user, created = User.objects.get_or_create(username='admin', defaults={'email': 'admin@selfing.cl', 'is_superuser': True, 'is_staff': True})
        if created:
            admin_user.set_password('admin123')
            admin_user.save()
            self.stdout.write(self.style.SUCCESS("Usuario Admin creado (admin / admin123)"))

        operador, created = User.objects.get_or_create(username='operador1', defaults={'email': 'operador1@selfing.cl', 'first_name': 'Juan', 'last_name': 'Pérez'})
        if created:
            operador.set_password('operador123')
            operador.save()
            OperatorProfile.objects.create(user=operador, rut="12345678-9", phone="+56912345678", terms_accepted=True)
            self.stdout.write(self.style.SUCCESS("Usuario Operador creado (operador1 / operador123)"))

        # ==========================================
        # 2. CREACIÓN DE EMPRESAS E INSTALACIONES
        # ==========================================
        empresa_a, _ = Company.objects.get_or_create(name='Empresa Prueba A', email='contacto@empresaa.cl')
        empresa_icv, _ = Company.objects.get_or_create(name='ICV', email='seguridad@icv.cl')
        empresa_chelech, _ = Company.objects.get_or_create(name='Chelech', email='control@chelech.cl')
        
        Installation.objects.get_or_create(company=empresa_a, name='Bodega Central')
        Installation.objects.get_or_create(company=empresa_icv, name='Instalación Nutria')
        Installation.objects.get_or_create(company=empresa_chelech, name='Bodega Chelech')
        self.stdout.write(self.style.SUCCESS("Empresas e Instalaciones creadas"))

        # ==========================================
        # 3. CREACIÓN DE TIPOS DE TURNO
        # ==========================================
        turno_dia, _ = ShiftType.objects.get_or_create(name='Turno Día', start_time=datetime.time(8, 30), end_time=datetime.time(16, 30), duration_hours=8, color='#007bff')
        turno_noche, _ = ShiftType.objects.get_or_create(name='Turno Noche', start_time=datetime.time(0, 30), end_time=datetime.time(8, 30), duration_hours=8, color='#343a40')
        self.stdout.write(self.style.SUCCESS("Tipos de Turnos creados"))

        # ==========================================
        # 4. ASIGNACIÓN DEL TURNO AL OPERADOR (FILTRADO INTELIGENTE)
        # ==========================================
        hoy = timezone.now().date()
        shift, _ = OperatorShift.objects.update_or_create(
            operator=operador, 
            date=hoy, 
            defaults={'shift_type': turno_noche}
        )
        
        # Limpiamos empresas previas y asignamos SÓLO ICV y Empresa A (Dejamos a Chelech fuera a propósito)
        shift.monitored_companies.clear()
        shift.monitored_companies.add(empresa_a, empresa_icv)
        self.stdout.write(self.style.SUCCESS(f"Turno Noche asignado. Monitorea: ICV y Empresa A (Chelech oculto)."))

        # ==========================================
        # 5. CREACIÓN DE CHECKLIST (JERARQUÍA PADRE/HIJO)
        # ==========================================
        ChecklistItem.objects.all().delete() # Reseteo limpio

        # -- Tareas Generales (Sin empresa, las ven todos) --
        item_ups = ChecklistItem.objects.create(description='Revisar estado de batería UPS', phase='start', order=1, requires_legal_check=False)
        item_ups.turnos_aplicables.add(turno_noche)
        
        item_sound = ChecklistItem.objects.create(description='Prueba de sonido de parlantes', phase='start', order=2, requires_legal_check=False)
        item_sound.turnos_aplicables.add(turno_noche)

        # -- TAREA PADRE: Wall de Visualización --
        padre_wall = ChecklistItem.objects.create(
            description='Revisión de Wall de visualización de cámaras asignadas', 
            phase='start', 
            order=3, 
            requires_legal_check=True
        )
        padre_wall.turnos_aplicables.add(turno_noche)

        # -- SUBTAREAS ICV (Hijas del Wall, asignadas a ICV) --
        icv_1 = ChecklistItem.objects.create(description='ICV Nutria', phase='start', parent=padre_wall, company=empresa_icv, order=1)
        icv_1.turnos_aplicables.add(turno_noche)
        
        icv_2 = ChecklistItem.objects.create(description='ICV Sarmiento', phase='start', parent=padre_wall, company=empresa_icv, order=2)
        icv_2.turnos_aplicables.add(turno_noche)

        # -- SUBTAREAS CHELECH (Hijas del Wall, asignadas a Chelech) --
        # NOTA: Estas NO deberían aparecerle al operador1 hoy, porque no tiene a Chelech en su turno.
        chl_1 = ChecklistItem.objects.create(description='Chelech Hogar', phase='start', parent=padre_wall, company=empresa_chelech, order=3)
        chl_1.turnos_aplicables.add(turno_noche)
        
        chl_2 = ChecklistItem.objects.create(description='Chelech Bodega central', phase='start', parent=padre_wall, company=empresa_chelech, order=4)
        chl_2.turnos_aplicables.add(turno_noche)

        # -- Tareas de Finalización --
        item_end = ChecklistItem.objects.create(description='Entregar turno a relevo', phase='end', order=1, requires_legal_check=True)
        item_end.turnos_aplicables.add(turno_noche)

        self.stdout.write(self.style.SUCCESS("Checklist jerárquico creado y asignado."))

        # ==========================================
        # 6. DATOS SECUNDARIOS (GPS, Servicios, etc.)
        # ==========================================
        MonitoredService.objects.get_or_create(name='Internet Fibra', defaults={'ip_address': '192.168.1.1'})
        
        sector, _ = Sector.objects.get_or_create(name='Sector Ruta 68', defaults={'company': empresa_icv})
        
        vehiculo, _ = Vehicle.objects.update_or_create(
            license_plate='ABCD-12', 
            defaults={
                'driver_name': 'Carlos Conductor', 
                'company': empresa_icv
            }
        )
        
        # SOLUCIÓN: Limpiamos las alertas viejas para evitar el error de duplicados
        GPSIncident.objects.all().delete()
        
        # Y creamos una alerta fresca para la prueba
        GPSIncident.objects.create(
            alert_type='Exceso de Velocidad',
            license_plate='ABCD-12',
            status='pending',
            location_text='Ruta 68 Km 12',
            incident_timestamp=timezone.now() - datetime.timedelta(minutes=10),
            sector_assigned=sector,
        )
        
        GPSNotificationSettings.objects.get_or_create(id=1, defaults={'instant_emails': 'admin@selfing.cl'})
        
        self.stdout.write(self.style.SUCCESS("\n¡Base de datos cargada con éxito!"))
        self.stdout.write("=====================================================")
        self.stdout.write("Prueba el filtrado iniciando sesión con:")
        self.stdout.write("👉 Operador: operador1 / operador123")
        self.stdout.write("Verás las tareas de ICV, pero NO las de Chelech.")
        self.stdout.write("=====================================================")