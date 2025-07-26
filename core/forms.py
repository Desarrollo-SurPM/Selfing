from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import UpdateLog, Email, ChecklistItem, Company, Installation, MonitoredService

class UpdateLogForm(forms.ModelForm):
    class Meta:
        model = UpdateLog
        fields = ['installation', 'message']
        widgets = {
            'installation': forms.HiddenInput(),
            'message': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Describa la novedad...'}),
        }

class EmailApprovalForm(forms.ModelForm):
    class Meta:
        model = Email
        fields = ['observations'] # Por ahora, solo permitimos editar las observaciones
        widgets = {
            'observations': forms.Textarea(attrs={'rows': 10}),
        }
class EmailForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        # Ya no necesitamos la lógica del 'operator' aquí
        super(EmailForm, self).__init__(*args, **kwargs)

        self.fields['updates'].label = "Novedades a Incluir"
        
        # --- ESTA ES LA LÓGICA CLAVE ---
        # Si el formulario se está enviando (es un POST y tiene datos)
        if self.data:
            try:
                # Tomamos el ID de la empresa que se envió en el formulario
                company_id = int(self.data.get('company'))
                # Actualizamos la lista de opciones válidas para el campo 'updates'
                # para que la validación funcione correctamente.
                self.fields['updates'].queryset = UpdateLog.objects.filter(
                    installation__company_id=company_id
                )
            except (ValueError, TypeError):
                # Si algo falla, usamos un queryset vacío para evitar más errores
                self.fields['updates'].queryset = UpdateLog.objects.none()
        # Si es una petición GET (la primera vez que se carga la página),
        # la lista de novedades empieza vacía.
        else:
            self.fields['updates'].queryset = UpdateLog.objects.none()

    class Meta:
        model = Email
        fields = ['company', 'updates', 'observations']
        widgets = {
            'updates': forms.CheckboxSelectMultiple,
            'observations': forms.Textarea(attrs={'rows': 5, 'placeholder': 'Añada observaciones adicionales aquí...'}),
        }

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
        fields = ['description']

class MonitoredServiceForm(forms.ModelForm):
    class Meta:
        model = MonitoredService
        fields = ['name', 'ip_address', 'is_active']
        labels = {
            'name': 'Nombre del Servicio',
            'ip_address': 'Dirección IP o Dominio',
            'is_active': '¿Activar monitoreo para este servicio?'
        }