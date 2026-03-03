from django import forms
from ..models import ChecklistItem, VirtualRoundLog, Installation, ShiftType


class ChecklistItemForm(forms.ModelForm):
    # Campo VIRTUAL para seleccionar múltiples instalaciones en la UI
    multi_installations = forms.ModelMultipleChoiceField(
        queryset=Installation.objects.all(),
        widget=forms.CheckboxSelectMultiple(),
        required=False,
        label="Instalaciones Específicas",
        help_text="Marque las casillas de las instalaciones que apliquen. Se generará una subtarea automática por cada una."
    )

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
        # Incluimos los campos necesarios del modelo
        fields = [
            'parent', 'description', 'phase', 'order',
            'company', 'dias_aplicables', 'turnos_aplicables',
            'unlock_delay', 'specific_time', 'alarm_trigger_delay',
            'is_sequential', 'requires_legal_check'
        ]
        labels = {
            'parent': 'Tarea Principal (Padre)',
            'description': 'Descripción de la Tarea',
            'phase': 'Fase del Turno',
            'order': 'Orden',
            'company': 'Empresa Específica',
            'unlock_delay': 'Tiempo de Bloqueo Inicial',
            'specific_time': 'Hora Específica',
            'alarm_trigger_delay': 'Tiempo para Alarma',
            'is_sequential': 'Bloqueo Secuencial',
            'requires_legal_check': 'Requiere Declaración Jurada (DDJJ)',
        }
        widgets = {
            'description': forms.TextInput(attrs={'placeholder': 'Ej: Realizar monitoreo de ICV'}),
            'unlock_delay': forms.TextInput(attrs={'placeholder': 'HH:MM:SS (Opcional)'}),
            'alarm_trigger_delay': forms.TextInput(attrs={'placeholder': 'HH:MM:SS (Opcional)'}),
            'specific_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Solo permitimos seleccionar como "Padre" a tareas que no tengan ya un padre (evitar niveles infinitos)
        self.fields['parent'].queryset = ChecklistItem.objects.filter(parent__isnull=True)
        self.fields['parent'].empty_label = "Ninguna (Esta es una tarea principal)"

        # Si estamos editando y tiene instalaciones en el campo ManyToMany, las precargamos en el campo virtual
        if self.instance and self.instance.pk:
            if self.instance.installations.exists():
                self.fields['multi_installations'].initial = self.instance.installations.all()
            
            if self.instance.dias_aplicables:
                self.fields['dias_aplicables'].initial = self.instance.dias_aplicables.split(',')

    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Guardamos los días seleccionados como una cadena separada por comas
        selected_days = self.cleaned_data.get('dias_aplicables')
        instance.dias_aplicables = ",".join(selected_days) if selected_days else ""
        
        if commit:
            instance.save()
            # Guardamos las relaciones M2M estándar (turnos_aplicables)
            self.save_m2m()
            
            # Sincronizamos el campo virtual 'multi_installations' con el real 'installations'
            # Al llamar a .set(), se dispara la señal m2m_changed en models.py
            selected_insts = self.cleaned_data.get('multi_installations')
            if selected_insts:
                instance.installations.set(selected_insts)
            else:
                instance.installations.clear()
                
        return instance

class VirtualRoundCompletionForm(forms.ModelForm):
    checked_installations = forms.ModelMultipleChoiceField(
        queryset=Installation.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Marque las instalaciones revisadas:"
    )

    class Meta:
        model = VirtualRoundLog
        fields = ['checked_installations']

    def __init__(self, *args, **kwargs):
        installations_queryset = kwargs.pop('installations_queryset', None)
        super(VirtualRoundCompletionForm, self).__init__(*args, **kwargs)
        if installations_queryset is not None:
            self.fields['checked_installations'].queryset = installations_queryset
        else:
            self.fields['checked_installations'].queryset = Installation.objects.all()
