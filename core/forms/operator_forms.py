import datetime
from django import forms
from django.utils import timezone
from django.db import transaction
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from ..models import OperatorProfile


class OperatorCreationForm(UserCreationForm):
    rut = forms.CharField(max_length=12, required=False, label="RUT", help_text="Formato: 12345678-9")
    phone = forms.CharField(max_length=20, required=False, label="Teléfono")
    address = forms.CharField(max_length=255, required=False, label="Dirección")
    terms_accepted = forms.BooleanField(required=False, label="Licencia de Uso Aceptada", help_text="Marcar si el operador ya firmó físicamente.")

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'first_name', 'last_name', 'email')

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            profile, created = OperatorProfile.objects.get_or_create(user=user)
            profile.rut = self.cleaned_data.get('rut')
            profile.phone = self.cleaned_data.get('phone')
            profile.address = self.cleaned_data.get('address')
            is_accepted = self.cleaned_data.get('terms_accepted')
            profile.terms_accepted = is_accepted
            if is_accepted:
                profile.terms_accepted_at = timezone.now()
            profile.save()
        return user


class OperatorChangeForm(forms.ModelForm):
    rut = forms.CharField(max_length=12, required=False, label="RUT", help_text="Formato: 12345678-9")
    phone = forms.CharField(max_length=20, required=False, label="Teléfono")
    address = forms.CharField(max_length=255, required=False, label="Dirección")
    terms_accepted = forms.BooleanField(required=False, label="Licencia de Uso Aceptada")

    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'is_active')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and hasattr(self.instance, 'profile'):
            self.fields['rut'].initial = self.instance.profile.rut
            self.fields['phone'].initial = self.instance.profile.phone
            self.fields['address'].initial = self.instance.profile.address
            self.fields['terms_accepted'].initial = self.instance.profile.terms_accepted

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            profile, created = OperatorProfile.objects.get_or_create(user=user)
            profile.rut = self.cleaned_data.get('rut')
            profile.phone = self.cleaned_data.get('phone')
            profile.address = self.cleaned_data.get('address')
            was_accepted = profile.terms_accepted
            is_accepted = self.cleaned_data.get('terms_accepted')
            profile.terms_accepted = is_accepted
            if is_accepted and not was_accepted:
                profile.terms_accepted_at = timezone.now()
            elif not is_accepted:
                profile.terms_accepted_at = None
            profile.save()
        return user
