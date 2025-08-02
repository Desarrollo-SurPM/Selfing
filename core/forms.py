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
    """
    Formulario para crear y editar ítems del checklist, con widgets
    personalizados para una mejor experiencia de usuario.
    """
    # Usamos MultipleChoiceField con checkboxes para seleccionar los días.
    dias_aplicables = forms.MultipleChoiceField(
        choices=ChecklistItem.DIAS_SEMANA,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Días de la Semana Aplicables",
        help_text="Marcar los días en que aplica. Dejar todos sin marcar para que aplique siempre."
    )

    # Usamos ModelMultipleChoiceField con checkboxes para los tipos de turno.
    turnos_aplicables = forms.ModelMultipleChoiceField(
        queryset=ShiftType.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Tipos de Turno Aplicables",
        help_text="Marcar los turnos en que aplica. Dejar sin marcar para que aplique a todos."
    )

    class Meta:
        model = ChecklistItem
        # Lista de campos que se mostrarán en el formulario, en el orden deseado.
        fields = [
            'description',
            'phase',
            'dias_aplicables',
            'turnos_aplicables',
            'alarm_trigger_delay', # <-- Aquí está el campo de la alarma
            'order',
        ]
        # Añadimos ayuda contextual para el campo de la alarma.
        help_texts = {
            'alarm_trigger_delay': "Formato: HH:MM:SS. Por ejemplo, para 1 hora y 30 minutos, ingrese '01:30:00'.",
        }
        # Añadimos un placeholder para guiar al usuario.
        widgets = {
            'alarm_trigger_delay': forms.TextInput(attrs={'placeholder': 'HH:MM:SS'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Si estamos editando una instancia que ya existe, precargamos
        # los días que estaban guardados como texto.
        if self.instance and self.instance.pk and self.instance.dias_aplicables:
            self.fields['dias_aplicables'].initial = self.instance.dias_aplicables.split(',')

    def save(self, commit=True):
        # Obtenemos la instancia del formulario sin guardarla aún en la BD.
        instance = super().save(commit=False)
        
        # Procesamos los datos del campo de días para guardarlos como una cadena.
        selected_days = self.cleaned_data.get('dias_aplicables')
        instance.dias_aplicables = ",".join(selected_days) if selected_days else ""
        
        # Si el formulario se guarda con commit=True (comportamiento por defecto),
        # guardamos la instancia principal y luego sus relaciones ManyToMany.
        if commit:
            instance.save()
            self.save_m2m() # Guarda la data de 'turnos_aplicables'
            
        return instance


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