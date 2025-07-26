from django.db import models
from django.contrib.auth.models import User

class Company(models.Model):
    name = models.CharField(max_length=100, unique=True)
    email = models.EmailField(blank=True, null=True, help_text="Correo para notificaciones generales de la empresa.")

    def __str__(self):
        return self.name

# 👇 --- NUEVO MODELO: INSTALACIÓN --- 👇
class Installation(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='installations')
    name = models.CharField(max_length=100, help_text="Ej: Campamento Sarmiento, Bodega Central, Oficina Pta. Arenas")
    address = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        # Evita que se repita el nombre de una instalación para la misma empresa
        unique_together = ('company', 'name')

    def __str__(self):
        return f"{self.name} ({self.company.name})"
# 👆 --- FIN DEL NUEVO MODELO --- 👆

class OperatorProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    def __str__(self):
        return self.user.username

class ChecklistItem(models.Model):
    description = models.CharField(max_length=255)
    def __str__(self):
        return self.description

class ChecklistLog(models.Model):
    operator = models.ForeignKey(User, on_delete=models.CASCADE)
    item = models.ForeignKey(ChecklistItem, on_delete=models.CASCADE)
    completed_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return f"{self.item.description} - {self.operator.username}"

# 👇 --- MODELO DE NOVEDADES ACTUALIZADO --- 👇
class UpdateLog(models.Model):
    operator = models.ForeignKey(User, on_delete=models.CASCADE)
    # AHORA SE RELACIONA CON UNA INSTALACIÓN, NO CON UNA EMPRESA
    installation = models.ForeignKey(Installation, on_delete=models.CASCADE)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Novedad para {self.installation.name} por {self.operator.username}"
# 👆 --- FIN DEL MODELO ACTUALIZADO --- 👆

class Email(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Borrador'),
        ('pending', 'Pendiente de Aprobación'),
        ('approved', 'Aprobado'),
        ('sent', 'Enviado'),
    ]
    operator = models.ForeignKey(User, on_delete=models.CASCADE, related_name='emails_sent')
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='emails_received')
    # Este campo podría necesitar una lógica más compleja ahora.
    # Por ahora, lo dejamos así, pero a futuro se podrían seleccionar novedades por instalación.
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
