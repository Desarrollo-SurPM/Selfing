import json
import re
from datetime import timedelta, datetime
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from ..models import (
    Company, UpdateLog, VirtualRoundLog, TraceabilityLog, ShiftNote, ChecklistLog
)
from ..forms import ShiftNoteForm
from ._helpers import get_active_shift, get_applicable_checklist_items


@login_required
def operator_dashboard(request):
    active_shift = get_active_shift(request.user)
    active_notes = ShiftNote.objects.filter(is_active=True)
    shift_note_form = ShiftNoteForm()

    start_blocked = False
    allowed_start_time = None

    if active_shift and not active_shift.actual_start_time:
        try:
            current_tz = timezone.get_current_timezone()
            scheduled_naive = datetime.combine(active_shift.date, active_shift.shift_type.start_time)
            if timezone.is_naive(scheduled_naive):
                scheduled_start = timezone.make_aware(scheduled_naive, current_tz)
            else:
                scheduled_start = scheduled_naive

            allowed_start_time = scheduled_start - timedelta(minutes=30)
            if timezone.now() < allowed_start_time:
                start_blocked = True
        except Exception as e:
            print(f"Error calculando bloqueo: {e}")

    context = {
        'active_shift': active_shift,
        'active_notes': active_notes,
        'shift_note_form': shift_note_form,
        'start_blocked': start_blocked,
        'allowed_start_time': allowed_start_time,
    }

    if active_shift and active_shift.actual_start_time:
        progress_tasks = {}
        completed_tasks_count = 0
        total_tasks = 2

        total_rondas_requeridas = 7
        rondas_completadas = VirtualRoundLog.objects.filter(operator_shift=active_shift).count()
        progress_tasks['rondas'] = {
            'completed': (rondas_completadas >= total_rondas_requeridas),
            'text': f"Rondas ({rondas_completadas}/{total_rondas_requeridas})"
        }
        if progress_tasks['rondas']['completed']:
            completed_tasks_count += 1

        if active_shift.monitored_companies.exists():
            empresas_objetivo = active_shift.monitored_companies.filter(installations__isnull=False).distinct()
        else:
            empresas_objetivo = Company.objects.filter(installations__isnull=False).distinct()

        ids_empresas_con_log = UpdateLog.objects.filter(
            operator_shift=active_shift,
            installation__company__in=empresas_objetivo
        ).values_list('installation__company_id', flat=True).distinct()

        progress_tasks['bitacora'] = {
            'completed': (len(ids_empresas_con_log) >= empresas_objetivo.count()),
            'text': f"Bitácora ({len(ids_empresas_con_log)}/{empresas_objetivo.count()})"
        }
        if progress_tasks['bitacora']['completed']:
            completed_tasks_count += 1

        context['progress_percentage'] = int((completed_tasks_count / total_tasks) * 100) if total_tasks > 0 else 0
        context['progress_tasks'] = progress_tasks

        applicable_items = get_applicable_checklist_items(active_shift)
        completed_in_shift_ids = ChecklistLog.objects.filter(operator_shift=active_shift).values_list('item_id', flat=True)
        pending_items = applicable_items.exclude(id__in=completed_in_shift_ids)
        pending_alarms_data = []
        for item in pending_items:
            if item.alarm_trigger_delay:
                due_time = active_shift.actual_start_time + item.alarm_trigger_delay
                pending_alarms_data.append({
                    'id': item.id,
                    'description': item.description,
                    'due_time': due_time.isoformat()
                })
        context['pending_alarms_json'] = json.dumps(pending_alarms_data)

        processed_logs = []
        traceability_logs_qs = TraceabilityLog.objects.filter(
            user=request.user,
            timestamp__gte=active_shift.actual_start_time
        ).order_by('-timestamp')
        for log in traceability_logs_qs:
            action_text = log.action
            match = re.search(r'Duración: (\d+)s', log.action)
            if match:
                seconds = int(match.group(1))
                if seconds < 60:
                    formatted_duration = f"{seconds} seg"
                elif seconds < 3600:
                    minutes, rem_seconds = divmod(seconds, 60)
                    formatted_duration = f"{minutes} min {rem_seconds} seg"
                else:
                    hours, rem_seconds = divmod(seconds, 3600)
                    rem_minutes, _ = divmod(rem_seconds, 60)
                    formatted_duration = f"{hours}h {rem_minutes} min"
                action_text = log.action.replace(f"Duración: {seconds}s", f"Duración: {formatted_duration}")
            processed_logs.append({'action': action_text, 'timestamp': log.timestamp})
        context['traceability_logs'] = processed_logs

        last_round = VirtualRoundLog.objects.filter(operator_shift=active_shift).order_by('-start_time').first()

        # Primera ronda: alarma a los 30 min del inicio del turno.
        # Rondas siguientes: alarma cada 60 min desde la última ronda iniciada.
        FIRST_ROUND_DELAY = timedelta(minutes=30)
        ROUND_INTERVAL = timedelta(hours=1)

        if last_round:
            next_round_due = last_round.start_time + ROUND_INTERVAL
        else:
            next_round_due = active_shift.actual_start_time + FIRST_ROUND_DELAY

        context['next_round_due_time'] = next_round_due.isoformat()
        context['active_round_id'] = request.session.get('active_round_id')

        round_completed_this_cycle = False
        if last_round:
            if timezone.now() < last_round.start_time + ROUND_INTERVAL:
                round_completed_this_cycle = True

        context['round_completed_this_cycle'] = round_completed_this_cycle
        context['shift_start_time_iso'] = active_shift.actual_start_time.isoformat()

    return render(request, 'operator/dashboard.html', context)


@login_required
def start_shift(request):
    if request.method == 'POST':
        shift_to_start = get_active_shift(request.user)

        if shift_to_start and shift_to_start.actual_start_time is None:
            current_tz = timezone.get_current_timezone()
            scheduled_naive = datetime.combine(shift_to_start.date, shift_to_start.shift_type.start_time)

            if timezone.is_naive(scheduled_naive):
                scheduled_start = timezone.make_aware(scheduled_naive, current_tz)
            else:
                scheduled_start = scheduled_naive

            now = timezone.now()
            time_difference = scheduled_start - now

            if time_difference > timedelta(minutes=30):
                allowed_entry_time = scheduled_start - timedelta(minutes=30)
                messages.error(request, f"Es muy temprano. Podrás iniciar turno a partir de las {allowed_entry_time.strftime('%H:%M')} (30 min antes).")
                return redirect('operator_dashboard')

            shift_to_start.actual_start_time = now
            shift_to_start.save()
            TraceabilityLog.objects.create(user=request.user, action="Inició turno.")
            messages.success(request, f"Turno '{shift_to_start.shift_type.name}' iniciado correctamente.")
        elif shift_to_start and shift_to_start.actual_start_time is not None:
            messages.warning(request, "El turno ya se encuentra iniciado.")
        else:
            messages.error(request, "No se pudo encontrar un turno pendiente para iniciar.")

    return redirect('operator_dashboard')
