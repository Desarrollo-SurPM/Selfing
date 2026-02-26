import datetime
from django import forms
from .models import GPSNotificationSettings
from django.core.exceptions import ValidationError
from django.utils import timezone
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
    """
    Formulario para crear y editar ítems del checklist, con widgets
    personalizados para una mejor experiencia de usuario.
    """
    # Usamos MultipleChoiceField con checkboxes para seleccionar los días.
    dias_aplicables = forms.MultipleChoiceField(
        choices=ChecklistItem.DIAS_SEMANA,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Días de la Semana Aplicables",
        help_text="Marcar los días en que aplica. Dejar todos sin marcar para que aplique siempre."
    )

    # Usamos ModelMultipleChoiceField con checkboxes para los tipos de turno.
    turnos_aplicables = forms.ModelMultipleChoiceField(
        queryset=ShiftType.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Tipos de Turno Aplicables",
        help_text="Marcar los turnos en que aplica. Dejar sin marcar para que aplique a todos."
    )

    class Meta:
        model = ChecklistItem
        # Lista de campos que se mostrarán en el formulario, en el orden deseado.
        fields = [
            'description',
            'phase',
            'dias_aplicables',
            'turnos_aplicables',
            'alarm_trigger_delay', # <-- Aquí está el campo de la alarma
            'order',
        ]
        # Añadimos ayuda contextual para el campo de la alarma.
        help_texts = {
            'alarm_trigger_delay': "Formato: HH:MM:SS. Por ejemplo, para 1 hora y 30 minutos, ingrese '01:30:00'.",
        }
        # Añadimos un placeholder para guiar al usuario.
        widgets = {
            'alarm_trigger_delay': forms.TextInput(attrs={'placeholder': 'HH:MM:SS'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Si estamos editando una instancia que ya existe, precargamos
        # los días que estaban guardados como texto.
        if self.instance and self.instance.pk and self.instance.dias_aplicables:
            self.fields['dias_aplicables'].initial = self.instance.dias_aplicables.split(',')

    def save(self, commit=True):
        # Obtenemos la instancia del formulario sin guardarla aún en la BD.
        instance = super().save(commit=False)
        
        # Procesamos los datos del campo de días para guardarlos como una cadena.
        selected_days = self.cleaned_data.get('dias_aplicables')
        instance.dias_aplicables = ",".join(selected_days) if selected_days else ""
        
        # Si el formulario se guarda con commit=True (comportamiento por defecto),
        # guardamos la instancia principal y luego sus relaciones ManyToMany.
        if commit:
            instance.save()
            self.save_m2m() # Guarda la data de 'turnos_aplicables'
            
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
        labels = {
            'name': 'Nombre del Servicio',
            'ip_address': 'Dirección IP o Dominio',
            'is_active': '¿Activar monitoreo para este servicio?'
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