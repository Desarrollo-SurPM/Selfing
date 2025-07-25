from django.db import models
from django.contrib.auth.models import User

class Company(models.Model):
    name = models.CharField(max_length=100, unique=True)
    email = models.EmailField()

    def __str__(self):
        return self.name

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

class UpdateLog(models.Model):
    operator = models.ForeignKey(User, on_delete=models.CASCADE)
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Novedad para {self.company.name} por {self.operator.username}"

class Email(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Borrador'),
        ('pending', 'Pendiente de Aprobación'),
        ('approved', 'Aprobado'),
        ('sent', 'Enviado'),
    ]
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