from collections import OrderedDict
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from ..models import UpdateLog, OperatorShift, ShiftNote, TraceabilityLog
from ..forms import UpdateLogEditForm, ShiftNoteForm
from ._helpers import get_active_shift, calculate_log_datetime
from .auth import is_supervisor


@login_required
def my_logbook_view(request):
    active_shift = get_active_shift(request.user)
    if not active_shift:
        return render(request, 'operator/logbook/personal.html', {'logbook_data': {}})

    logs_del_turno_qs = UpdateLog.objects.filter(
        operator_shift=active_shift
    ).select_related('installation', 'installation__company')
    logs_list = list(logs_del_turno_qs)
    logs_list.sort(key=lambda x: (x.installation.company.name, x.installation.name, calculate_log_datetime(x)))

    logbook_data = {}
    for log in logs_list:
        if log.installation and log.installation.company:
            company_name = log.installation.company.name
            installation_name = log.installation.name
            if company_name not in logbook_data:
                logbook_data[company_name] = {}
            if installation_name not in logbook_data[company_name]:
                logbook_data[company_name][installation_name] = []
            logbook_data[company_name][installation_name].append(log)

    return render(request, 'operator/logbook/personal.html', {
        'logbook_data': logbook_data,
        'shift_start_time': active_shift.actual_start_time
    })


@login_required
def edit_update_log(request, log_id):
    log_entry = get_object_or_404(UpdateLog, id=log_id, operator_shift__operator=request.user)
    if not log_entry.is_edited:
        log_entry.original_message = log_entry.message

    if request.method == 'POST':
        form = UpdateLogEditForm(request.POST, request.FILES, instance=log_entry)
        if form.is_valid():
            log_entry.is_edited = True
            log_entry.edited_at = timezone.now()
            form.save()
            TraceabilityLog.objects.create(
                user=request.user,
                action=f"Editó una entrada de la bitácora para la instalación '{log_entry.installation.name}'."
            )
            messages.success(request, 'La novedad ha sido actualizada correctamente.')
            return redirect('my_logbook')
    else:
        form = UpdateLogEditForm(instance=log_entry)

    return render(request, 'operator/update_log/edit.html', {'form': form, 'log_entry': log_entry})


@login_required
def delete_update_log(request, log_id):
    log_entry = get_object_or_404(UpdateLog, id=log_id, operator_shift__operator=request.user)
    if request.method == 'POST':
        try:
            log_entry.delete()
            TraceabilityLog.objects.create(
                user=request.user,
                action=f"Eliminó una entrada de la bitácora para la instalación '{log_entry.installation.name}'."
            )
            return JsonResponse({'status': 'success', 'message': 'Novedad eliminada.'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': f'Error al eliminar: {e}'}, status=400)
    return render(request, 'operator/update_log/confirm_delete.html', {'log_entry': log_entry})


@login_required
def full_logbook_view(request):
    shift_ids_to_show = []
    active_shifts = OperatorShift.objects.filter(
        actual_start_time__isnull=False,
        actual_end_time__isnull=True
    ).order_by('actual_start_time')

    if active_shifts.exists():
        shift_ids_to_show.extend(list(active_shifts.values_list('id', flat=True)))
        previous_shifts = OperatorShift.objects.filter(actual_end_time__isnull=False).order_by('-actual_end_time')[:2]
        shift_ids_to_show.extend(list(previous_shifts.values_list('id', flat=True)))
    else:
        previous_shifts = OperatorShift.objects.filter(actual_end_time__isnull=False).order_by('-actual_end_time')[:3]
        shift_ids_to_show.extend(list(previous_shifts.values_list('id', flat=True)))

    logs = UpdateLog.objects.filter(
        operator_shift_id__in=shift_ids_to_show
    ).select_related(
        'operator_shift__shift_type', 'operator_shift__operator', 'installation__company'
    ).order_by('operator_shift__actual_start_time', 'created_at')

    logs_by_shift = OrderedDict()
    for log in logs:
        shift = log.operator_shift
        if shift not in logs_by_shift:
            logs_by_shift[shift] = []
        logs_by_shift[shift].append(log)

    return render(request, 'operator/logbook/full.html', {'logs_by_shift': logs_by_shift})


@login_required
@user_passes_test(is_supervisor)
def current_logbook_view(request):
    active_shifts = OperatorShift.objects.filter(
        actual_start_time__isnull=False,
        actual_end_time__isnull=True
    ).select_related('operator', 'shift_type')
    current_logbook_data = {}

    for shift in active_shifts:
        operator_name = f"{shift.operator.first_name} {shift.operator.last_name}"
        logs_list = list(UpdateLog.objects.filter(
            operator_shift=shift
        ).select_related('installation', 'installation__company'))
        logs_list.sort(key=lambda x: calculate_log_datetime(x))

        if logs_list:
            logbook_data = {}
            for log in logs_list:
                if log.installation and log.installation.company:
                    company_name = log.installation.company.name
                    installation_name = log.installation.name
                    if company_name not in logbook_data:
                        logbook_data[company_name] = {}
                    if installation_name not in logbook_data[company_name]:
                        logbook_data[company_name][installation_name] = []
                    logbook_data[company_name][installation_name].append(log)

            current_logbook_data[operator_name] = {'shift': shift, 'logbook_data': logbook_data}

    return render(request, 'operator/logbook/current.html', {'current_logbook_data': current_logbook_data})


@login_required
def dismiss_shift_note(request, note_id):
    if request.method == 'POST':
        note = get_object_or_404(ShiftNote, id=note_id)
        note.is_active = False
        note.save()
        messages.info(request, "Nota marcada como leída.")
    return redirect('operator_dashboard')


@login_required
def create_shift_note_modal(request):
    if request.method == 'POST':
        form = ShiftNoteForm(request.POST)
        if form.is_valid():
            note = form.save(commit=False)
            note.created_by = request.user
            note.save()
            messages.success(request, "Nota guardada con éxito.")
        else:
            messages.error(request, "Error al guardar la nota.")
    return redirect('operator_dashboard')
