from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
# Importación consolidada de todos los modelos necesarios
from .models import (
    UpdateLog, Email, ChecklistItem, Company, Installation, MonitoredService,
    ShiftType, OperatorShift, VirtualRoundLog
)

# --- Formularios de Registros del Operador ---

class UpdateLogForm(forms.ModelForm):
    class Meta:
        model = UpdateLog
        fields = ['installation', 'message']
        widgets = {
            'installation': forms.HiddenInput(),
            'message': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Describa la novedad...'}),
        }

class EmailForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(EmailForm, self).__init__(*args, **kwargs)
        self.fields['updates'].label = "Novedades a Incluir"
        # Lógica para que la validación funcione con checkboxes dinámicos
        if self.data:
            try:
                company_id = int(self.data.get('company'))
                self.fields['updates'].queryset = UpdateLog.objects.filter(
                    installation__company_id=company_id
                )
            except (ValueError, TypeError):
                self.fields['updates'].queryset = UpdateLog.objects.none()
        else:
            self.fields['updates'].queryset = UpdateLog.objects.none()

    class Meta:
        model = Email
        fields = ['company', 'updates', 'observations']
        widgets = {
            'updates': forms.CheckboxSelectMultiple,
            'observations': forms.Textarea(attrs={'rows': 5, 'placeholder': 'Añada observaciones adicionales aquí...'}),
        }

class VirtualRoundCompletionForm(forms.ModelForm):
    checked_installations = forms.ModelMultipleChoiceField(
        queryset=Installation.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label="Marque las instalaciones que fueron revisadas durante la ronda:"
    )
    class Meta:
        model = VirtualRoundLog
        fields = ['checked_installations']


# --- Formularios de Gestión del Administrador ---

class EmailApprovalForm(forms.ModelForm):
    class Meta:
        model = Email
        fields = ['observations']
        widgets = {'observations': forms.Textarea(attrs={'rows': 10})}

class OperatorCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'first_name', 'last_name', 'email')

class OperatorChangeForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'is_active')

class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ['name', 'email']

class InstallationForm(forms.ModelForm):
    class Meta:
        model = Installation
        fields = ['company', 'name', 'address']

class ChecklistItemForm(forms.ModelForm):
    class Meta:
        model = ChecklistItem
        fields = ['description', 'phase', 'trigger_offset_minutes']
        labels = {
            'description': 'Descripción de la Tarea',
            'phase': 'Fase del Turno',
            'trigger_offset_minutes': 'Minutos desde el inicio para activar alerta',
        }
        widgets = {
            'description': forms.TextInput(attrs={'placeholder': 'Ej: Revisar cámaras del sector A'}),
        }

class MonitoredServiceForm(forms.ModelForm):
    class Meta:
        model = MonitoredService
        fields = ['name', 'ip_address', 'is_active']
        labels = {
            'name': 'Nombre del Servicio',
            'ip_address': 'Dirección IP o Dominio',
            'is_active': '¿Activar monitoreo para este servicio?'
        }

class ShiftTypeForm(forms.ModelForm):
    class Meta:
        model = ShiftType
        fields = ['name', 'start_time', 'end_time', 'duration_hours']
        labels = {
            'name': 'Nombre del Turno',
            'start_time': 'Hora de Inicio',
            'end_time': 'Hora de Término',
            'duration_hours': 'Duración (horas)',
        }
        widgets = {
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
        }

class OperatorShiftForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(OperatorShiftForm, self).__init__(*args, **kwargs)
        # --- LÓGICA AÑADIDA ---
        # Filtramos el campo 'operator' para que solo muestre usuarios
        # que NO son superusuarios (es decir, solo operadores).
        self.fields['operator'].queryset = User.objects.filter(is_superuser=False)

    class Meta:
        model = OperatorShift
        fields = ['operator', 'shift_type', 'date']
        labels = {
            'operator': 'Operador',
            'shift_type': 'Turno',
            'date': 'Fecha',
        }
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
        }