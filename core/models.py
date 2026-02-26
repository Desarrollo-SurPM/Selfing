from django.db import models
from django.contrib.auth.models import User

class Company(models.Model):
    name = models.CharField(max_length=100, unique=True)
    # El campo 'email' ahora es un TextField para guardar múltiples correos
    email = models.TextField(
        blank=True,
        null=True,
        help_text="Correos para notificaciones, separados por comas."
    )

    def __str__(self):
        return self.name

class Installation(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='installations')
    name = models.CharField(max_length=100, help_text="Ej: Campamento Sarmiento, Bodega Central, Oficina Pta. Arenas")
    address = models.CharField(max_length=255, blank=True, null=True)
    class Meta:
        unique_together = ('company', 'name')
    def __str__(self):
        return f"{self.name} ({self.company.name})"

class OperatorProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    def __str__(self):
        return self.user.username
    
class ShiftType(models.Model):
    name = models.CharField(max_length=100, unique=True, help_text="Ej: Turno Mañana, Turno Noche")
    start_time = models.TimeField()
    end_time = models.TimeField()
    duration_hours = models.PositiveIntegerField(help_text="Duración del turno en horas (ej: 8, 12)")
    color = models.CharField(
        max_length=7, 
        default="#CCCCCC", 
        help_text="Código de color Hex (ej: #FF0000 para rojo)"
    )
    def __str__(self):
        return f"{self.name} ({self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')})"

class OperatorShift(models.Model):
    operator = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shifts')
    shift_type = models.ForeignKey(ShiftType, on_delete=models.PROTECT)
    date = models.DateField()
    actual_start_time = models.DateTimeField(null=True, blank=True)
    actual_end_time = models.DateTimeField(null=True, blank=True)
    
    # --- NUEVO CAMPO ---
    monitored_companies = models.ManyToManyField(
        Company, 
        blank=True, 
        related_name='assigned_shifts',
        verbose_name="Empresas Específicas",
        help_text="Seleccione solo si el turno es restringido (ej: Mañana fin de semana). Deje vacío para monitorear TODAS."
    )
    # -------------------

    class Meta:
        unique_together = ('operator', 'date')
    
    def __str__(self):
        return f"Turno de {self.operator.username} ({self.date})"

class ChecklistItem(models.Model):
    """
    Representa una tarea individual dentro de la lista de verificación de un operador.
    """
    # --- Campos de Identificación de la Tarea ---
    description = models.CharField(
        max_length=255,
        verbose_name="Descripción de la Tarea"
    )
    phase = models.CharField(
        max_length=20,
        choices=[
            ('start', 'Inicio de Turno'),
            ('during', 'Durante el Turno'),
            ('end', 'Finalización de Turno')
        ],
        default='during',
        verbose_name="Fase del Turno"
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name="Orden de Visualización",
        help_text="Un número más bajo se muestra primero."
    )

    # --- Campos de Programación y Aplicabilidad ---
    DIAS_SEMANA = [
        (0, 'Lunes'), (1, 'Martes'), (2, 'Miércoles'), (3, 'Jueves'),
        (4, 'Viernes'), (5, 'Sábado'), (6, 'Domingo')
    ]
    dias_aplicables = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name="Días de la Semana Aplicables",
        help_text="Marcar los días en que aplica. Dejar todos sin marcar para que aplique siempre."
    )
    turnos_aplicables = models.ManyToManyField(
        'ShiftType', # Usa el string para evitar importaciones circulares
        blank=True,
        verbose_name="Tipos de Turno Aplicables",
        help_text="Marcar los turnos en que aplica. Dejar sin marcar para que aplique a todos."
    )

    # --- Funcionalidad de Alarma ---
    alarm_trigger_delay = models.DurationField(
        null=True,
        blank=True,
        verbose_name="Alarma de Tarea Pendiente",
        help_text="Establecer un tiempo para la alarma (ej: '1:30' para 1 hora y 30 mins) si la tarea no se completa. Se calcula desde el inicio del turno."
    )

    class Meta:
        ordering = ['phase', 'order']
        verbose_name = "Ítem de Checklist"
        verbose_name_plural = "Ítems de Checklist"

    def __str__(self):
        return f"[{self.get_phase_display()}] {self.description}"


# core/models.py

class ChecklistLog(models.Model):
    operator_shift = models.ForeignKey(OperatorShift, on_delete=models.CASCADE, related_name='checklist_logs')
    item = models.ForeignKey(ChecklistItem, on_delete=models.CASCADE)
    completed_at = models.DateTimeField(auto_now_add=True)

    # --- 👇 CAMPO NUEVO AÑADIDO 👇 ---
    observacion = models.TextField(blank=True, null=True, verbose_name="Observación")
    # --- 👆 FIN DEL CAMPO NUEVO 👆 ---

    class Meta:
        unique_together = ('operator_shift', 'item')

# --- 👇 CAMBIO #2 👇 ---
class VirtualRoundLog(models.Model):
    # Se asocia a un turno específico.
    operator_shift = models.ForeignKey(OperatorShift, on_delete=models.CASCADE, related_name='round_logs')
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    checked_installations = models.TextField(blank=True, null=True, help_text="Lista de instalaciones revisadas, separadas por comas")

    def get_duration_display(self):
        if self.duration_seconds is None:
            return "N/A"
        
        seconds = self.duration_seconds
        if seconds < 60:
            return f"{seconds} seg"
        elif seconds < 3600:
            minutes = seconds // 60
            rem_seconds = seconds % 60
            return f"{minutes} min {rem_seconds} seg"
        else:
            hours = seconds // 3600
            rem_minutes = (seconds % 3600) // 60
            return f"{hours}h {rem_minutes} min"
    # --- 👆 FIN DE LA FUNCIÓN AÑADIDA 👆 ---
    def __str__(self):
        return f"Ronda de {self.operator_shift.operator.username} - iniciada a las {self.start_time.strftime('%H:%M')}"

class UpdateLog(models.Model):
    operator_shift = models.ForeignKey(OperatorShift, on_delete=models.CASCADE, related_name='update_logs')
    installation = models.ForeignKey(Installation, on_delete=models.CASCADE)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Campo existente
    is_sent = models.BooleanField(default=False, verbose_name="¿Enviado en reporte?")

    # Campos existentes del Sprint 1
    manual_timestamp = models.TimeField(
        null=True, 
        blank=True, 
        verbose_name="Hora Manual del Evento"
    )
    is_edited = models.BooleanField(
        default=False, 
        verbose_name="¿Ha sido editado?"
    )
    original_message = models.TextField(
        blank=True, 
        null=True, 
        verbose_name="Mensaje Original"
    )
    edited_at = models.DateTimeField(
        null=True, 
        blank=True, 
        verbose_name="Fecha de Edición"
    )

    # --- 👇 NUEVO CAMPO PARA ADJUNTOS 👇 ---
    attachment = models.FileField(
        upload_to='novedades/%Y/%m/%d/',
        blank=True,
        null=True,
        verbose_name="Adjunto (Foto/Video)",
        help_text="Formatos sugeridos: JPG, PNG, MP4"
    )
    # --- 👆 FIN DE NUEVO CAMPO 👆 ---

    def __str__(self):
        return f"Novedad para {self.installation.name} por {self.operator_shift.operator.username}"

    # --- 👇 NUEVO MÉTODO HELPER 👇 ---
    def is_image(self):
        if not self.attachment:
            return False
        name = self.attachment.name.lower()
        return name.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))
    # --- 👆 FIN MÉTODO HELPER 👆 ---
class Email(models.Model):
    operator = models.ForeignKey(User, on_delete=models.CASCADE, related_name='emails_sent')
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='emails_received')
    updates = models.ManyToManyField(UpdateLog) 
    observations = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=10, choices=[('sent', 'Enviado')], default='sent')
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return f"Correo para {self.company.name} - {self.status}"
class TraceabilityLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    action = models.CharField(max_length=255)
    timestamp = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return f"{self.user.username} - {self.action} a las {self.timestamp}"

class MonitoredService(models.Model):
    name = models.CharField(max_length=100, unique=True, help_text="Ej: Conexión a Internet, Servidor de Archivos")
    ip_address = models.CharField(max_length=100, help_text="Dirección IP o dominio a monitorear")
    is_active = models.BooleanField(default=True, help_text="Marcar para activar el monitoreo de este servicio")
    def __str__(self):
        return self.name

class ServiceStatusLog(models.Model):
    service = models.ForeignKey(MonitoredService, on_delete=models.CASCADE, related_name='logs')
    is_up = models.BooleanField()
    timestamp = models.DateTimeField(auto_now_add=True)
    response_time = models.FloatField(null=True, blank=True, help_text="Tiempo de respuesta en ms")
    def __str__(self):
        status = "Activo" if self.is_up else "Caído"
        return f"{self.service.name} - {status} a las {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"

class TurnReport(models.Model):
    # --- CAMBIO AQUÍ: AÑADIR null=True ---
    operator_shift = models.OneToOneField(
        OperatorShift,
        on_delete=models.CASCADE,
        related_name='turn_report',
        null=True  # Permite que el campo esté vacío temporalmente
    )
    # --- FIN DEL CAMBIO ---
    operator = models.ForeignKey(User, on_delete=models.CASCADE, related_name='turn_reports')
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(auto_now_add=True)
    pdf_report = models.FileField(upload_to='turn_reports/%Y/%m/%d/')
    is_signed = models.BooleanField(default=False)
    signed_at = models.DateTimeField(null=True, blank=True)
    def __str__(self):
        return f"Reporte de {self.operator.username} - {self.end_time.strftime('%Y-%m-%d %H:%M')}"
    
class EmergencyContact(models.Model):
    name = models.CharField(max_length=100, verbose_name="Nombre del Contacto (Ej: Ambulancia, Bomberos, Supervisor)")
    phone_number = models.CharField(max_length=20, verbose_name="Número de Teléfono")
    
    company = models.ForeignKey(
        Company, 
        on_delete=models.CASCADE, 
        related_name='emergency_contacts',
        null=True, 
        blank=True,
        help_text="Dejar en blanco si es un contacto general (Ej: Ambulancia)."
    )
    installation = models.ForeignKey(
        Installation, 
        on_delete=models.CASCADE, 
        related_name='emergency_contacts',
        null=True, 
        blank=True,
        help_text="Opcional: especificar si este contacto es solo para una instalación."
    )

    class Meta:
        ordering = ['company__name', 'installation__name', 'name']
        verbose_name = "Contacto de Emergencia"
        verbose_name_plural = "Contactos de Emergencia"

    def __str__(self):
        if self.installation:
            return f"{self.name} - {self.installation.name}"
        if self.company:
            return f"{self.name} - {self.company.name}"
        return f"{self.name} (General)"

class ShiftNote(models.Model):
    message = models.TextField(verbose_name="Mensaje de la Nota")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="created_shift_notes")
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True, verbose_name="¿Está activa?")

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Nota de Turno"
        verbose_name_plural = "Notas de Turno"

    def __str__(self):
        return f"Nota de {self.created_by.username} el {self.created_at.strftime('%d/%m/%Y')}"

# Modelos para Seguridad Vehicular
class Vehicle(models.Model):
    license_plate = models.CharField(max_length=20, unique=True, verbose_name="Patente")
    driver_name = models.CharField(max_length=100, verbose_name="Conductor")
    vehicle_type = models.CharField(max_length=50, choices=[
        ('truck', 'Camión'),
        ('van', 'Furgoneta'),
        ('car', 'Automóvil'),
        ('motorcycle', 'Motocicleta'),
        ('other', 'Otro')
    ], default='truck', verbose_name="Tipo de Vehículo")
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='vehicles', verbose_name="Empresa")
    is_active = models.BooleanField(default=True, verbose_name="Activo")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Vehículo"
        verbose_name_plural = "Vehículos"
        ordering = ['license_plate']
    
    def __str__(self):
        return f"{self.license_plate} - {self.driver_name}"

class VehiclePosition(models.Model):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='positions')
    latitude = models.DecimalField(max_digits=10, decimal_places=8, verbose_name="Latitud")
    longitude = models.DecimalField(max_digits=11, decimal_places=8, verbose_name="Longitud")
    speed = models.FloatField(default=0, verbose_name="Velocidad (km/h)")
    timestamp = models.DateTimeField(auto_now_add=True)
    is_connected = models.BooleanField(default=True, verbose_name="Conectado")
    
    class Meta:
        verbose_name = "Posición de Vehículo"
        verbose_name_plural = "Posiciones de Vehículos"
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.vehicle.license_plate} - {self.timestamp.strftime('%d/%m/%Y %H:%M')}"

class VehicleAlert(models.Model):
    ALERT_TYPES = [
        ('speed', 'Exceso de Velocidad'),
        ('weather', 'Mal Clima'),
        ('traffic', 'Atascamiento'),
        ('route_cut', 'Corte de Ruta'),
        ('connection', 'Sin Conexión'),
        ('stopped', 'Tiempo Detenido Excesivo')
    ]
    
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='alerts')
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPES, verbose_name="Tipo de Alerta")
    message = models.TextField(verbose_name="Mensaje")
    latitude = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True)
    longitude = models.DecimalField(max_digits=11, decimal_places=8, null=True, blank=True)
    is_resolved = models.BooleanField(default=False, verbose_name="Resuelta")
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = "Alerta de Vehículo"
        verbose_name_plural = "Alertas de Vehículos"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.vehicle.license_plate} - {self.get_alert_type_display()}"

class VehicleRoute(models.Model):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='routes')
    start_time = models.DateTimeField(verbose_name="Hora de Inicio")
    end_time = models.DateTimeField(null=True, blank=True, verbose_name="Hora de Fin")
    start_latitude = models.DecimalField(max_digits=10, decimal_places=8)
    start_longitude = models.DecimalField(max_digits=11, decimal_places=8)
    end_latitude = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True)
    end_longitude = models.DecimalField(max_digits=11, decimal_places=8, null=True, blank=True)
    total_distance = models.FloatField(default=0, verbose_name="Distancia Total (km)")
    average_speed = models.FloatField(default=0, verbose_name="Velocidad Promedio (km/h)")
    max_speed = models.FloatField(default=0, verbose_name="Velocidad Máxima (km/h)")
    stop_time_minutes = models.IntegerField(default=0, verbose_name="Tiempo Detenido (minutos)")
    weather_conditions = models.TextField(blank=True, null=True, verbose_name="Condiciones Climáticas")
    
    class Meta:
        verbose_name = "Ruta de Vehículo"
        verbose_name_plural = "Rutas de Vehículos"
        ordering = ['-start_time']
    
    def __str__(self):
        return f"{self.vehicle.license_plate} - {self.start_time.strftime('%d/%m/%Y %H:%M')}"


## nuevo modelo ##
class Sector(models.Model):
    """
    Representa una zona geográfica o sector operativo para cruzar con la ubicación del correo.
    """
    name = models.CharField(max_length=150, unique=True, verbose_name="Nombre del Sector")
    geofence_polygon = models.JSONField(
        blank=True, 
        null=True, 
        verbose_name="Coordenadas de la Geocerca",
        help_text="Formato: [[lat1, lon1], [lat2, lon2], [lat3, lon3], ...]"
    )
    description = models.TextField(blank=True, null=True, verbose_name="Descripción o Referencias")
    
    # Opcional: Vincularlo a una empresa si Selfing maneja multitenencia estricta en la vista del operador
    company = models.ForeignKey(
        'Company', 
        on_delete=models.CASCADE, 
        related_name='sectors', 
        null=True, 
        blank=True,
        verbose_name="Empresa Asociada"
    )

    class Meta:
        verbose_name = "Sector"
        verbose_name_plural = "Sectores"
        ordering = ['name']

    def __str__(self):
        return self.name


class SectorContact(models.Model):
    """
    Encargados asociados a cada sector que serán contactados durante una alerta.
    """
    sector = models.ForeignKey(Sector, on_delete=models.CASCADE, related_name='contacts', verbose_name="Sector")
    name = models.CharField(max_length=150, verbose_name="Nombre del Encargado")
    phone = models.CharField(max_length=50, verbose_name="Teléfono")
    email = models.EmailField(blank=True, null=True, verbose_name="Correo Electrónico")
    is_active = models.BooleanField(default=True, verbose_name="¿Está activo?")
    
    class Meta:
        verbose_name = "Contacto de Sector"
        verbose_name_plural = "Contactos de Sector"
        ordering = ['sector__name', 'name']

    def __str__(self):
        return f"{self.name} - {self.sector.name}"


class GPSIncident(models.Model):
    """
    Alerta GPS parseada automáticamente desde el correo electrónico. Totalmente independiente.
    """
    STATUS_CHOICES = [
        ('pending', 'Pendiente'),
        ('resolved', 'Resuelto'),
        ('ignored', 'Ignorado (Falso Positivo)')
    ]

    # Datos extraídos exclusivamente del correo electrónico (texto plano)
    alert_type = models.CharField(max_length=100, verbose_name="Tipo de Alerta", help_text="Ej: Botón de Pánico, Ralentí, Colisión")
    unit_id = models.CharField(max_length=100, blank=True, null=True, verbose_name="ID de Unidad")
    license_plate = models.CharField(max_length=20, verbose_name="Codigo Enap")
    driver_name = models.CharField(max_length=150, blank=True, null=True, verbose_name="Conductor")
    location_text = models.TextField(verbose_name="Ubicación (Texto)")
    incident_timestamp = models.DateTimeField(verbose_name="Fecha y Hora del Incidente")
    latitude = models.FloatField(blank=True, null=True, verbose_name="Latitud")
    longitude = models.FloatField(blank=True, null=True, verbose_name="Longitud")
    maps_url = models.URLField(max_length=1000, blank=True, null=True, verbose_name="Enlace de Google Maps")
    
    # Metadatos del sistema
    cknowledged_at = models.DateTimeField(blank=True, null=True, verbose_name="Hora de toma del caso")
    received_at = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Recepción (Sistema)")
    
    # Relaciones calculadas por el Service Layer
    sector_assigned = models.ForeignKey(Sector, on_delete=models.SET_NULL, null=True, blank=True, related_name='incidents', verbose_name="Sector Asignado")

    # Gestión de Resolución (Triage por el Operador)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Estado")
    operator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_incidents', verbose_name="Operador que resolvió")
    who_answered = models.CharField(max_length=150, blank=True, null=True, verbose_name="¿Quién contestó la llamada?")
    operator_notes = models.TextField(blank=True, null=True, verbose_name="Notas de Resolución")
    
    # Métricas para el Excel mensual
    resolved_at = models.DateTimeField(null=True, blank=True, verbose_name="Fecha y Hora de Resolución")
    response_time_seconds = models.PositiveIntegerField(null=True, blank=True, verbose_name="Tiempo de Respuesta (Segundos)", help_text="Calculado automáticamente al resolver.")

    class Meta:
        verbose_name = "Incidente GPS"
        verbose_name_plural = "Incidentes GPS"
        ordering = ['-incident_timestamp']

    def __str__(self):
        return f"{self.alert_type} - {self.license_plate} ({self.get_status_display()})"
    
    def calculate_response_time(self):
        """Calcula el tiempo de respuesta en segundos al guardar la resolución"""
        if self.resolved_at and self.received_at:
            delta = self.resolved_at - self.received_at
            self.response_time_seconds = int(delta.total_seconds())


class GPSNotificationSettings(models.Model):
    """
    Configuración global para los destinatarios de correos del módulo GPS.
    Actúa como un Singleton (solo debe existir un registro).
    """
    instant_emails = models.TextField(
        verbose_name="Correos para Alertas Instantáneas (Triage)",
        help_text="Separados por coma (,). Ej: jefe_turno@enap.cl, supervisor@selfing.cl",
        default="jefatura@tuempresa.cl"
    )
    monthly_emails = models.TextField(
        verbose_name="Correos para Reporte Mensual (Excel)",
        help_text="Separados por coma (,). Ej: gerencia@enap.cl, admin@selfing.cl",
        default="admin@tuempresa.cl"
    )

    class Meta:
        verbose_name = "Configuración de Notificaciones GPS"
        verbose_name_plural = "Configuración de Notificaciones GPS"

    def __str__(self):
        return "Gestión de Destinatarios GPS"

    def get_instant_emails_list(self):
        """Convierte el texto separado por comas en una lista de Python."""
        return [email.strip() for email in self.instant_emails.split(',') if email.strip()]

    def get_monthly_emails_list(self):
        """Convierte el texto separado por comas en una lista de Python."""
        return [email.strip() for email in self.monthly_emails.split(',') if email.strip()]