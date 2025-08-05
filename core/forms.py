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
    """
    Formulario simplificado para que el operador envíe su reporte de turno
    con una observación final.
    """
    class Meta:
        model = Email
        # El único campo que el operador debe llenar es la observación.
        fields = ['final_observation']
        widgets = {
            'final_observation': forms.Textarea(attrs={'rows': 5, 'placeholder': 'Añada un resumen u observación final sobre las novedades de su turno...'}),
        }
        labels = {
            'final_observation': "Observación Final del Turno"
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

class EmailApprovalForm(forms.Form):
    """
    Este formulario se genera dinámicamente en la vista para permitir al admin
    aprobar o rechazar novedades individualmente.
    """
    # Usamos un campo que aceptará una lista de IDs de las novedades aprobadas.
    approved_updates = forms.ModelMultipleChoiceField(
        queryset=UpdateLog.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False # Es posible que no se apruebe ninguna.
    )
    # El administrador también puede añadir sus propias observaciones.
    admin_observations = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4}),
        required=False,
        label="Observaciones Adicionales para el Correo Final"
    )

    def __init__(self, *args, **kwargs):
        # El queryset de las novedades se pasará desde la vista.
        update_logs_queryset = kwargs.pop('update_logs', None)
        super().__init__(*args, **kwargs)
        if update_logs_queryset is not None:
            self.fields['approved_updates'].queryset = update_logs_queryset

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