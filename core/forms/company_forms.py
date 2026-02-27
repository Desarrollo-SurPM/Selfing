from django import forms
from ..models import Company, Installation


class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ['name', 'email']


class InstallationForm(forms.ModelForm):
    class Meta:
        model = Installation
        fields = ['company', 'name', 'address']
