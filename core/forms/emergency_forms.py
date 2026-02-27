from django import forms
from ..models import EmergencyContact


class EmergencyContactForm(forms.ModelForm):
    class Meta:
        model = EmergencyContact
        fields = ['name', 'phone_number', 'company', 'installation']
        labels = {
            'name': 'Nombre del Contacto',
            'phone_number': 'Número de Teléfono',
            'company': 'Empresa Asociada (Opcional)',
            'installation': 'Instalación Específica (Opcional)',
        }
