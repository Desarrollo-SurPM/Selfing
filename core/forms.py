from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import UpdateLog, Email, ChecklistItem, Company

class UpdateLogForm(forms.ModelForm):
    class Meta:
        model = UpdateLog
        fields = ['company', 'message']
        widgets = {
            'message': forms.Textarea(attrs={'rows': 4}),
        }

class EmailForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        operator = kwargs.pop('operator', None)
        super().__init__(*args, **kwargs)
        if operator:
            self.fields['updates'].queryset = UpdateLog.objects.filter(operator=operator, company=self.initial.get('company'))

    class Meta:
        model = Email
        fields = ['company', 'updates', 'observations']
        widgets = {
            'updates': forms.CheckboxSelectMultiple,
            'observations': forms.Textarea(attrs={'rows': 5}),
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
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Nombre de la empresa cliente'}),
            'email': forms.EmailInput(attrs={'placeholder': 'Correo para notificaciones'}),
        }