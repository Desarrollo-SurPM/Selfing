import datetime
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta
from ..models import UpdateLog, Company, Installation, OperatorShift


class UpdateLogForm(forms.ModelForm):
    class Meta:
        model = UpdateLog
        fields = ['installation', 'message', 'manual_timestamp', 'attachment']
        widgets = {
            'installation': forms.HiddenInput(),
            'message': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': 'Describa la novedad...',
                'spellcheck': 'true',
                'lang': 'es-LA'
            }),
            'manual_timestamp': forms.TimeInput(attrs={
                'type': 'text',
                'pattern': '[0-9]{2}:[0-9]{2}',
                'placeholder': 'HH:MM'
            }, format='%H:%M'),
            'attachment': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'manual_timestamp': 'Hora del Evento (Opcional - Formato HH:MM)',
            'attachment': 'Adjuntar Foto o Video (Opcional)'
        }

    def clean_manual_timestamp(self):
        timestamp_time = self.cleaned_data.get('manual_timestamp')
        if timestamp_time:
            now_dt = timezone.localtime(timezone.now())
            try:
                event_dt_today = timezone.make_aware(datetime.datetime.combine(now_dt.date(), timestamp_time))
            except ValueError:
                raise ValidationError("Formato de hora inválido. Use HH:MM.")
            
            # Le damos una tolerancia de 5 minutos al futuro por si hay desfase de relojes
            future_buffer = (now_dt + timedelta(minutes=5)).time()
            
            # Si la hora ingresada es mayor al tiempo actual (+5 mins buffer), asume el día de ayer
            if timestamp_time > future_buffer:
                event_dt = event_dt_today - timedelta(days=1)
            else:
                event_dt = event_dt_today
                
            if event_dt > now_dt:
                raise ValidationError("La fecha y hora del evento no pueden ser futuras.")
            if now_dt - event_dt > timedelta(hours=24):
                raise ValidationError("No puedes registrar eventos de más de 24 horas de antigüedad.")
                
        return timestamp_time


class UpdateLogEditForm(forms.ModelForm):
    class Meta:
        model = UpdateLog
        fields = ['message', 'manual_timestamp', 'attachment']
        widgets = {
            'message': forms.Textarea(attrs={'rows': 4}),
            'manual_timestamp': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
            'attachment': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'message': 'Corregir Novedad',
            'manual_timestamp': 'Hora Manual del Evento (Opcional)',
            'attachment': 'Cambiar Adjunto (Dejar vacío para mantener el actual)'
        }

    def clean_manual_timestamp(self):
        timestamp_time = self.cleaned_data.get('manual_timestamp')
        if timestamp_time:
            now_dt = timezone.localtime(timezone.now())
            try:
                event_dt_today = timezone.make_aware(datetime.datetime.combine(now_dt.date(), timestamp_time))
            except ValueError:
                raise ValidationError("Formato de hora inválido. Use HH:MM.")
            
            # Le damos una tolerancia de 5 minutos al futuro por si hay desfase de relojes
            future_buffer = (now_dt + timedelta(minutes=5)).time()
            
            # Si la hora ingresada es mayor al tiempo actual (+5 mins buffer), asume el día de ayer
            if timestamp_time > future_buffer:
                event_dt = event_dt_today - timedelta(days=1)
            else:
                event_dt = event_dt_today
                
            if event_dt > now_dt:
                raise ValidationError("La fecha y hora del evento no pueden ser futuras.")
            if now_dt - event_dt > timedelta(hours=24):
                raise ValidationError("No puedes registrar eventos de más de 24 horas de antigüedad.")
                
        return timestamp_time


class AdminUpdateLogForm(forms.ModelForm):
    company = forms.ModelChoiceField(
        queryset=Company.objects.order_by('name'),
        label="Empresa",
        required=True
    )
    target_shift = forms.ModelChoiceField(
        queryset=OperatorShift.objects.none(),
        label="Asignar Novedad al Turno",
        required=True,
        empty_label=None
    )

    class Meta:
        model = UpdateLog
        fields = ['installation', 'message', 'manual_timestamp', 'attachment']
        labels = {
            'installation': 'Instalación',
            'message': 'Mensaje de la Novedad',
            'manual_timestamp': 'Hora del Evento (Opcional)',
            'attachment': 'Adjuntar Foto/Video'
        }
        widgets = {
            'message': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Ej: Apertura de sucursal OK.'}),
            'manual_timestamp': forms.TimeInput(attrs={'type': 'time'}),
            'attachment': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        cycle_shifts_qs = kwargs.pop('cycle_shifts', None)
        super().__init__(*args, **kwargs)
        if cycle_shifts_qs is not None:
            self.fields['target_shift'].queryset = cycle_shifts_qs
            self.fields['target_shift'].label_from_instance = lambda obj: f"{obj.operator.username} - {obj.shift_type.name} ({obj.date.strftime('%d/%m')})"
        else:
            self.fields['target_shift'].queryset = OperatorShift.objects.none()

        self.fields['installation'].queryset = Installation.objects.none()

        if 'company' in self.data:
            try:
                company_id = int(self.data.get('company'))
                self.fields['installation'].queryset = Installation.objects.filter(company_id=company_id).order_by('name')
            except (ValueError, TypeError):
                pass
        elif self.instance.pk and self.instance.installation:
            self.fields['company'].initial = self.instance.installation.company_id
            self.fields['installation'].queryset = Installation.objects.filter(company=self.instance.installation.company).order_by('name')
            self.fields['installation'].initial = self.instance.installation_id

        if self.instance.pk and self.instance.operator_shift_id:
            current_shift_queryset = self.fields['target_shift'].queryset
            if current_shift_queryset.filter(pk=self.instance.operator_shift_id).exists():
                self.fields['target_shift'].initial = self.instance.operator_shift_id

    def clean(self):
        cleaned_data = super().clean()
        timestamp_time = cleaned_data.get('manual_timestamp')
        shift = cleaned_data.get('target_shift')

        if timestamp_time and shift:
            shift_date = shift.date
            try:
                event_dt_base = timezone.make_aware(datetime.datetime.combine(shift_date, timestamp_time))
            except ValueError:
                raise ValidationError("Formato de hora inválido. Use HH:MM.")

            event_dt = event_dt_base
            now_dt = timezone.localtime(timezone.now())

            if shift.shift_type.end_time < shift.shift_type.start_time and \
               timestamp_time < shift.shift_type.start_time and \
               timestamp_time <= shift.shift_type.end_time:
                event_dt = event_dt_base + timedelta(days=1)

            if event_dt > now_dt:
                raise ValidationError("La fecha y hora del evento no pueden ser futuras.")

        return cleaned_data


class OperatorObservationForm(forms.Form):
    observacion_final = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4, 'placeholder': 'Añada una observación general de su turno...'}),
        required=False,
        label="Observación Final del Turno"
    )
