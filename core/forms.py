import datetime
from django import forms
from .models import GPSNotificationSettings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db import transaction
from .models import OperatorProfile
from datetime import timedelta
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
# Importación consolidada de todos los modelos necesarios
from .models import (
    UpdateLog, ChecklistItem, Company, Installation, MonitoredService,
    ShiftType, OperatorShift, VirtualRoundLog, EmergencyContact, ShiftNote
)

# --- Formularios de Registros del Operador ---

class UpdateLogForm(forms.ModelForm):
    class Meta:
        model = UpdateLog
        # Agregamos 'attachment'
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
            # Widget para adjuntar
            'attachment': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'manual_timestamp': 'Hora del Evento (Opcional - Formato HH:MM)',
            'attachment': 'Adjuntar Foto o Video (Opcional)'
        }
        # La función clean_manual_timestamp no necesita cambios por ahora
        def clean_manual_timestamp(self):
            timestamp_time = self.cleaned_data.get('manual_timestamp')
            if timestamp_time:
                now_dt = timezone.localtime(timezone.now())
            # Combina la hora ingresada con la fecha actual
                try: # Añadido try-except por si la conversión falla
                    event_dt_today = timezone.make_aware(datetime.datetime.combine(now_dt.date(), timestamp_time))
                except ValueError:
                     raise ValidationError("Formato de hora inválido. Use HH:MM.")

            # Si la hora ingresada es mayor que la hora actual (ej: 20:30 > 00:11)
            # asumimos que ocurrió el día anterior
                if timestamp_time > now_dt.time():
                    event_dt = event_dt_today - timedelta(days=1)
                else:
                    event_dt = event_dt_today

            # Ahora comparamos el datetime completo
                if event_dt > now_dt:
                    raise ValidationError("La fecha y hora del evento no pueden ser futuras.")

            # Opcional: Limitar qué tan atrás puede ir la fecha/hora manual
            # Por ejemplo, no permitir eventos de más de 24 horas atrás
                if now_dt - event_dt > timedelta(hours=24):
                     raise ValidationError("No puedes registrar eventos de más de 24 horas de antigüedad.")

            return timestamp_time # Devolvemos solo la hora, como espera el TimeField
# --- 👇 NUEVO FORMULARIO PARA EDICIÓN 👇 ---
class UpdateLogEditForm(forms.ModelForm):
    class Meta:
        model = UpdateLog
        # Agregamos 'attachment'
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

    # Añadimos la misma validación que en el formulario de creación
    def clean_manual_timestamp(self):
        timestamp_time = self.cleaned_data.get('manual_timestamp')
        if timestamp_time:
            now_dt = timezone.localtime(timezone.now())
            
            event_dt_today = timezone.make_aware(datetime.datetime.combine(now_dt.date(), timestamp_time))

            if timestamp_time > now_dt.time():
                event_dt = event_dt_today - timedelta(days=1)
            else:
                event_dt = event_dt_today

            if event_dt > now_dt:
                raise ValidationError("La fecha y hora del evento no pueden ser futuras.")

            if now_dt - event_dt > timedelta(hours=24):
                 raise ValidationError("No puedes registrar eventos de más de 24 horas de antigüedad.")
                 
        return timestamp_time
class AdminUpdateLogForm(forms.ModelForm):
    """
    Formulario para que el administrador añada una novedad desde la vista de revisión.
    Ahora con dropdowns dependientes Y selección de turno.
    """
    company = forms.ModelChoiceField(
        queryset=Company.objects.order_by('name'),
        label="Empresa",
        required=True
    )
    target_shift = forms.ModelChoiceField(
        queryset=OperatorShift.objects.none(), # Se poblará desde la vista
        label="Asignar Novedad al Turno",
        required=True,
        empty_label=None # Evita una opción vacía
    )

    class Meta:
        model = UpdateLog
        # Agregamos 'attachment'
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

    # *** CORRECCIÓN APLICADA AQUÍ ***
    def __init__(self, *args, **kwargs):
        # 1. Extrae el argumento personalizado ANTES de llamar a super()
        cycle_shifts_qs = kwargs.pop('cycle_shifts', None)

        # 2. Llama al constructor de la clase padre SIN el argumento personalizado
        super().__init__(*args, **kwargs) # <- Esta línea ya no dará error

        # 3. Configura el queryset del campo 'target_shift' AHORA
        if cycle_shifts_qs is not None:
            self.fields['target_shift'].queryset = cycle_shifts_qs
            # Define cómo se mostrará cada opción en el dropdown
            self.fields['target_shift'].label_from_instance = lambda obj: f"{obj.operator.username} - {obj.shift_type.name} ({obj.date.strftime('%d/%m')})"
        else:
             # Si no se pasa, asegúrate de que el queryset esté vacío
             self.fields['target_shift'].queryset = OperatorShift.objects.none()


        # 4. Lógica existente para el dropdown dependiente de instalación
        self.fields['installation'].queryset = Installation.objects.none()

        if 'company' in self.data: # Si el formulario se envió con datos
            try:
                company_id = int(self.data.get('company'))
                self.fields['installation'].queryset = Installation.objects.filter(company_id=company_id).order_by('name')
            except (ValueError, TypeError):
                pass # Mantiene el queryset vacío si hay error
        elif self.instance.pk and self.instance.installation: # Si se está editando una instancia existente
             # Pre-selecciona la compañía
            self.fields['company'].initial = self.instance.installation.company_id
            # Puebla las instalaciones de esa compañía
            self.fields['installation'].queryset = Installation.objects.filter(company=self.instance.installation.company).order_by('name')
             # Pre-selecciona la instalación
            self.fields['installation'].initial = self.instance.installation_id

        # 5. Preseleccionar el turno si la instancia lo tiene y está en el queryset permitido
        if self.instance.pk and self.instance.operator_shift_id:
             current_shift_queryset = self.fields['target_shift'].queryset
             if current_shift_queryset.filter(pk=self.instance.operator_shift_id).exists():
                 self.fields['target_shift'].initial = self.instance.operator_shift_id

    # No olvides incluir la validación de clean_manual_timestamp de respuestas anteriores
    def clean(self):
        cleaned_data = super().clean()
        timestamp_time = cleaned_data.get('manual_timestamp')
        shift = cleaned_data.get('target_shift')

        if timestamp_time and shift:
            # Si tenemos la hora y el turno, validamos con la fecha del turno
            shift_date = shift.date
            
            try:
                # Combinamos la fecha del TURNO con la hora manual
                event_dt_base = timezone.make_aware(datetime.datetime.combine(shift_date, timestamp_time))
            except ValueError:
                 raise ValidationError("Formato de hora inválido. Use HH:MM.")

            event_dt = event_dt_base # Asumimos que es el mismo día
            now_dt = timezone.localtime(timezone.now())

            # Lógica de cruce de medianoche (basada en el turno)
            if shift.shift_type.end_time < shift.shift_type.start_time and \
               timestamp_time < shift.shift_type.start_time and \
               timestamp_time <= shift.shift_type.end_time:
                # El evento ocurrió en la madrugada del día siguiente al de la fecha del turno
                event_dt = event_dt_base + timedelta(days=1)
            
            # Validación final: no puede ser en el futuro
            if event_dt > now_dt:
                raise ValidationError(
                    "La fecha y hora del evento no pueden ser futuras."
                )

        return cleaned_data

class VirtualRoundCompletionForm(forms.ModelForm):
    # 1. SOBREESCRIBIMOS el campo explícitamente para que sea de Selección Múltiple
    # (Django no lo adivina porque en el modelo es un TextField)
    checked_installations = forms.ModelMultipleChoiceField(
        queryset=Installation.objects.none(), # Se llena dinámicamente después
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Marque las instalaciones revisadas:"
    )

    class Meta:
        model = VirtualRoundLog
        fields = ['checked_installations']

    def __init__(self, *args, **kwargs):
        # Extraemos el argumento personalizado
        installations_queryset = kwargs.pop('installations_queryset', None)
        super(VirtualRoundCompletionForm, self).__init__(*args, **kwargs)
        
        # 2. Asignamos las instalaciones filtradas al campo que ya creamos arriba
        if installations_queryset is not None:
            self.fields['checked_installations'].queryset = installations_queryset
        else:
            self.fields['checked_installations'].queryset = Installation.objects.all()


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
            
            # Guardar el estado de la licencia
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
            
            # Lógica para la licencia
            was_accepted = profile.terms_accepted
            is_accepted = self.cleaned_data.get('terms_accepted')
            profile.terms_accepted = is_accepted
            
            if is_accepted and not was_accepted:
                profile.terms_accepted_at = timezone.now()
            elif not is_accepted:
                profile.terms_accepted_at = None
                
            profile.save()
        return user
    rut = forms.CharField(max_length=12, required=False, label="RUT", help_text="Formato: 12345678-9")
    phone = forms.CharField(max_length=20, required=False, label="Teléfono")
    address = forms.CharField(max_length=255, required=False, label="Dirección")

    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'is_active')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pre-poblar los campos del perfil si el usuario ya existe y tiene perfil
        if self.instance and hasattr(self.instance, 'profile'):
            self.fields['rut'].initial = self.instance.profile.rut
            self.fields['phone'].initial = self.instance.profile.phone
            self.fields['address'].initial = self.instance.profile.address

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            profile, created = OperatorProfile.objects.get_or_create(user=user)
            profile.rut = self.cleaned_data.get('rut')
            profile.phone = self.cleaned_data.get('phone')
            profile.address = self.cleaned_data.get('address')
            profile.save()
        return user
class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ['name', 'email']

class InstallationForm(forms.ModelForm):
    class Meta:
        model = Installation
        fields = ['company', 'name', 'address']

class ChecklistItemForm(forms.ModelForm):
    dias_aplicables = forms.MultipleChoiceField(
        choices=ChecklistItem.DIAS_SEMANA,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Días Aplicables",
        help_text="Marcar los días en que aplica. Dejar sin marcar para que aplique siempre."
    )

    turnos_aplicables = forms.ModelMultipleChoiceField(
        queryset=ShiftType.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Turnos Aplicables",
        help_text="Marcar los turnos en que aplica. Dejar sin marcar para aplicar a todos."
    )

    class Meta:
        model = ChecklistItem
        fields = [
            'parent', 'description', 'phase', 'order',
            'company', 'installation',
            'dias_aplicables', 'turnos_aplicables',
            'unlock_delay', 'alarm_trigger_delay',
            'is_sequential', 'requires_legal_check'
        ]
        labels = {
            'parent': 'Tarea Principal (Padre)',
            'description': 'Descripción de la Tarea',
            'phase': 'Fase del Turno',
            'order': 'Orden',
            'company': 'Empresa Específica',
            'installation': 'Instalación Específica',
            'unlock_delay': 'Tiempo de Bloqueo Inicial',
            'alarm_trigger_delay': 'Tiempo para Alarma',
            'is_sequential': 'Bloqueo Secuencial',
            'requires_legal_check': 'Requiere Declaración Jurada (DDJJ)',
        }
        widgets = {
            'description': forms.TextInput(attrs={'placeholder': 'Ej: Realizar monitoreo de ICV'}),
            'unlock_delay': forms.TextInput(attrs={'placeholder': 'HH:MM:SS (Opcional)'}),
            'alarm_trigger_delay': forms.TextInput(attrs={'placeholder': 'HH:MM:SS (Opcional)'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Limitar las opciones de "parent" a tareas que no sean hijas (para evitar más de 1 nivel de anidación)
        self.fields['parent'].queryset = ChecklistItem.objects.filter(parent__isnull=True)
        self.fields['parent'].empty_label = "Ninguna (Esta es una tarea principal)"
        
        # Filtros de empresa/instalación predeterminados
        self.fields['installation'].queryset = Installation.objects.all()

        if self.instance and self.instance.pk and self.instance.dias_aplicables:
            self.fields['dias_aplicables'].initial = self.instance.dias_aplicables.split(',')

    def save(self, commit=True):
        instance = super().save(commit=False)
        selected_days = self.cleaned_data.get('dias_aplicables')
        instance.dias_aplicables = ",".join(selected_days) if selected_days else ""
        
        if commit:
            instance.save()
            self.save_m2m()
        return instance

class OperatorObservationForm(forms.Form):
    """
    Nuevo formulario simple para que el operador añada una observación final.
    """
    observacion_final = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4, 'placeholder': 'Añada una observación general de su turno...'}),
        required=False,
        label="Observación Final del Turno"
    )

class MonitoredServiceForm(forms.ModelForm):
    class Meta:
        model = MonitoredService
        fields = ['name', 'ip_address', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Conexión a Internet Pta. Arenas'}),
            'ip_address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '192.168.1.1 o dominio.com'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'})
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
        self.fields['operator'].queryset = User.objects.filter(is_superuser=False)
    monitored_companies = forms.ModelMultipleChoiceField(
        queryset=Company.objects.all(),
        widget=forms.CheckboxSelectMultiple, # O SelectMultiple con UI mejorada
        required=False,
        label="Seleccionar Empresas a Monitorear (Opcional)",
        help_text="Marque las empresas SOLO si es un turno parcial. Si deja todo desmarcado, el operador monitoreará TODAS las empresas."
    )
    class Meta:
        model = OperatorShift
        fields = ['operator', 'shift_type', 'date', 'monitored_companies']
        labels = {
            'operator': 'Operador',
            'shift_type': 'Turno',
            'date': 'Fecha',
        }
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'monitored_companies': forms.CheckboxSelectMultiple(),
        }

class ShiftNoteForm(forms.ModelForm):
    class Meta:
        model = ShiftNote
        fields = ['message']
        widgets = {
            'message': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Escribe aquí una nota, pendiente o instrucción para el próximo turno...'}),
        }
        labels = {
            'message': 'Nueva Nota para el Siguiente Turno'
        }
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

class GPSNotificationSettingsForm(forms.ModelForm):
    class Meta:
        model = GPSNotificationSettings
        fields = ['instant_emails', 'monthly_emails']
        widgets = {
            'instant_emails': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'gerente@enap.cl, supervisor@selfing.cl'}),
            'monthly_emails': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'auditoria@enap.cl, admin@selfing.cl'}),
        }