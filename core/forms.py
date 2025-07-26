from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import UpdateLog, Email, ChecklistItem, Company, Installation

class UpdateLogForm(forms.ModelForm):
    class Meta:
        model = UpdateLog
        fields = ['installation', 'message']
        widgets = {
            'installation': forms.HiddenInput(),
            'message': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Describa la novedad...'}),
        }

class EmailForm(forms.ModelForm):
    # 👇 --- ESTA ES LA CORRECCIÓN PARA EL ERROR TypeError --- 👇
    def __init__(self, *args, **kwargs):
        # Extraemos 'operator' antes de llamar al padre para que no cause un error
        operator = kwargs.pop('operator', None)
        super(EmailForm, self).__init__(*args, **kwargs)
        
        # Filtramos el queryset de novedades si se proporciona un operador
        if operator and 'company' in self.initial:
            company_id = self.initial['company']
            self.fields['updates'].queryset = UpdateLog.objects.filter(
                installation__company_id=company_id
            )
    # 👆 --- FIN DE LA CORRECCIÓN --- 👆

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

class InstallationForm(forms.ModelForm):
    class Meta:
        model = Installation
        fields = ['company', 'name', 'address']

class ChecklistItemForm(forms.ModelForm):
    class Meta:
        model = ChecklistItem
        fields = ['description']