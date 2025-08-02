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
    class TurnPhase(models.TextChoices):
        INICIO = 'INICIO', 'Inicio de Turno'
        DURANTE = 'DURANTE', 'Durante el Turno'
        FIN = 'FIN', 'Finalización de Turno'
    description = models.CharField(max_length=255)
    phase = models.CharField(
        max_length=10,
        choices=TurnPhase.choices,
        default=TurnPhase.INICIO
    )
    trigger_offset_minutes = models.PositiveIntegerField(
        default=0,
        help_text="Minutos desde el inicio del turno para que esta tarea sea relevante."
    )
    # Campo para la reordenación
    order = models.PositiveIntegerField(default=0, help_text="Posición de la tarea en la lista")
    
    class Meta:
        # Ordenar por el nuevo campo 'order' por defecto
        ordering = ['order']

    def __str__(self):
        return f"[{self.get_phase_display()}] {self.description}"

class ChecklistLog(models.Model):
    # Se asocia a un turno específico para saber a qué jornada pertenece.
    operator_shift = models.ForeignKey(OperatorShift, on_delete=models.CASCADE, related_name='checklist_logs')
    item = models.ForeignKey(ChecklistItem, on_delete=models.CASCADE)
    completed_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return f"{self.item.description} - {self.operator_shift.operator.username}"

# --- 👇 CAMBIO #2 👇 ---
class VirtualRoundLog(models.Model):
    # Se asocia a un turno específico.
    operator_shift = models.ForeignKey(OperatorShift, on_delete=models.CASCADE, related_name='round_logs')
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    checked_installations = models.TextField(blank=True, null=True, help_text="Lista de instalaciones revisadas, separadas por comas")
    def __str__(self):
        return f"Ronda de {self.operator_shift.operator.username} - iniciada a las {self.start_time.strftime('%H:%M')}"

# --- 👇 CAMBIO #3 👇 ---
class UpdateLog(models.Model):
    # Se asocia a un turno específico.
    operator_shift = models.ForeignKey(OperatorShift, on_delete=models.CASCADE, related_name='update_logs')
    installation = models.ForeignKey(Installation, on_delete=models.CASCADE)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return f"Novedad para {self.installation.name} por {self.operator_shift.operator.username}"


# --- (El resto de los modelos no tienen cambios) ---
class Email(models.Model):
    STATUS_CHOICES = [('draft', 'Borrador'), ('pending', 'Pendiente de Aprobación'), ('approved', 'Aprobado'), ('sent', 'Enviado')]
    operator = models.ForeignKey(User, on_delete=models.CASCADE, related_name='emails_sent')
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='emails_received')
    updates = models.ManyToManyField(UpdateLog) 
    observations = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    created_at = models.DateTimeField(auto_now_add=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_emails')
    approved_at = models.DateTimeField(null=True, blank=True)
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