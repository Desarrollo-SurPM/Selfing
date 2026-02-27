from django import forms
from ..models import MonitoredService


class MonitoredServiceForm(forms.ModelForm):
    class Meta:
        model = MonitoredService
        fields = ['name', 'ip_address', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Conexión a Internet Pta. Arenas'}),
            'ip_address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '192.168.1.1 o dominio.com'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'})
        }
