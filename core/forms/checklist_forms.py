from django import forms
from ..models import ChecklistItem, VirtualRoundLog, Installation, ShiftType


class ChecklistItemForm(forms.ModelForm):
    # Campo VIRTUAL (no toca la BD) con CheckboxSelectMultiple para mejor UX
    multi_installations = forms.ModelMultipleChoiceField(
        queryset=Installation.objects.all(),
        widget=forms.CheckboxSelectMultiple(),
        required=False,
        label="Instalaciones Específicas",
        help_text="Marca las casillas de las instalaciones que apliquen. Se generará una tarea independiente por cada una."
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
        # Ocultamos 'installation' (el original) e incluimos 'multi_installations' virtual
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
        self.fields['parent'].queryset = ChecklistItem.objects.filter(parent__isnull=True)
        self.fields['parent'].empty_label = "Ninguna (Esta es una tarea principal)"

        # Si estamos editando y ya tiene una instalación asignada en la BD, la preseleccionamos
        if self.instance and self.instance.pk and self.instance.installation:
            self.fields['multi_installations'].initial = [self.instance.installation.pk]

        if self.instance and self.instance.pk and self.instance.dias_aplicables:
            self.fields['dias_aplicables'].initial = self.instance.dias_aplicables.split(',')

    def save(self, commit=True):
        instance = super().save(commit=False)
        is_creating = instance.pk is None  # Saber si es un registro nuevo o una edición
        
        selected_days = self.cleaned_data.get('dias_aplicables')
        instance.dias_aplicables = ",".join(selected_days) if selected_days else ""
        
        selected_insts = self.cleaned_data.get('multi_installations')
        
        if commit:
            if not selected_insts:
                instance.installation = None
                instance.save()
                self.save_m2m()
            else:
                # 1. Guardamos la tarea original asignándole la PRIMERA instalación elegida
                instance.installation = selected_insts[0]
                instance.save()
                self.save_m2m()
                
                # 2. CLONACIÓN: Si estamos creando (no editando) y eligió más de 1 instalación, clonamos la tarea
                if is_creating and len(selected_insts) > 1:
                    for inst in selected_insts[1:]:
                        clone = ChecklistItem.objects.create(
                            description=instance.description,
                            phase=instance.phase,
                            order=instance.order,
                            unlock_delay=instance.unlock_delay,
                            specific_time=instance.specific_time, # Copiamos la hora específica
                            dias_aplicables=instance.dias_aplicables,
                            alarm_trigger_delay=instance.alarm_trigger_delay,
                            parent=instance.parent,
                            is_sequential=instance.is_sequential,
                            requires_legal_check=instance.requires_legal_check,
                            company=instance.company,
                            installation=inst # Asignamos la instalación clonada
                        )
                        clone.turnos_aplicables.set(self.cleaned_data.get('turnos_aplicables', []))
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
