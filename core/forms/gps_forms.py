from django import forms
from ..models import GPSNotificationSettings


class GPSNotificationSettingsForm(forms.ModelForm):
    class Meta:
        model = GPSNotificationSettings
        fields = ['instant_emails', 'monthly_emails']
        widgets = {
            'instant_emails': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'gerente@enap.cl, supervisor@selfing.cl'}),
            'monthly_emails': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'auditoria@enap.cl, admin@selfing.cl'}),
        }
