from django import forms
from django.contrib.auth.models import User
from ..models import ShiftType, OperatorShift, ShiftNote, Company


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
    monitored_companies = forms.ModelMultipleChoiceField(
        queryset=Company.objects.all(),
        widget=forms.CheckboxSelectMultiple,
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

    def __init__(self, *args, **kwargs):
        super(OperatorShiftForm, self).__init__(*args, **kwargs)
        self.fields['operator'].queryset = User.objects.filter(is_superuser=False)


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
