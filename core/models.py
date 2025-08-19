from django.db import models
from django.contrib.auth.models import User

class Company(models.Model):
    name = models.CharField(max_length=100, unique=True)
    email = models.EmailField(blank=True, null=True, help_text="Correo para notificaciones generales de la empresa.")
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
    def __str__(self):
        return f"{self.name} ({self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')})"

class OperatorShift(models.Model):
    operator = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shifts')
    shift_type = models.ForeignKey(ShiftType, on_delete=models.PROTECT)
    date = models.DateField()
    actual_start_time = models.DateTimeField(null=True, blank=True)
    actual_end_time = models.DateTimeField(null=True, blank=True)
    class Meta:
        unique_together = ('operator', 'date')
    def __str__(self):
        return f"Turno de {self.operator.username} el {self.date.strftime('%Y-%m-%d')} ({self.shift_type.name})"

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
    
    # --- CAMPO AÑADIDO ---
    # Para saber si esta novedad ya fue incluida en un correo.
    is_sent = models.BooleanField(default=False, verbose_name="¿Enviado en reporte?")

    # --- 👇 NUEVOS CAMPOS PARA SPRINT 1 👇 ---
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
    # --- 👆 FIN DE NUEVOS CAMPOS 👆 ---

    def __str__(self):
        return f"Novedad para {self.installation.name} por {self.operator_shift.operator.username}"


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

