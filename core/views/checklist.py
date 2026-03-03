from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.utils import timezone
from ..models import ChecklistItem, ChecklistLog, TraceabilityLog
from ._helpers import get_active_shift, get_applicable_checklist_items


@login_required
def checklist_index_view(request):
    """
    Vista del menú principal del checklist. 
    Muestra los 3 botones para seleccionar la fase del turno.
    """
    active_shift = get_active_shift(request.user)
    if not active_shift:
        return redirect('operator_dashboard')

    return render(request, 'operator/checklist_index.html', {
        'active_shift': active_shift
    })


@login_required
def checklist_phase_view(request, phase):
    """
    Vista dinámica que carga las tareas de una fase específica.
    Prepara los datos en JSON para inyectarlos al Frontend (Layout de 2 columnas).
    """
    # Validación de seguridad para que no ingresen URLs inventadas
    if phase not in ['start', 'during', 'end']:
        return redirect('checklist_index')

    active_shift = get_active_shift(request.user)
    if not active_shift:
        return redirect('operator_dashboard')

    # 1. Filtramos las tareas SOLO por la fase solicitada
    checklist_items = get_applicable_checklist_items(active_shift).filter(phase=phase)
    
    # 2. Obtenemos los logs (progreso) de esas tareas en el turno actual
    logs_del_turno = ChecklistLog.objects.filter(operator_shift=active_shift, item__phase=phase)
    completed_logs_dict = {log.item.id: log for log in logs_del_turno}

    # 3. Serializamos los datos para Javascript
    tasks_for_js = []
    for item in checklist_items:
        log = completed_logs_dict.get(item.id)
        is_completed = log is not None and log.status == 'completed'

        duration_str = log.get_duration_display() if is_completed else '00:00'
        started_at_iso = log.started_at.isoformat() if log and log.started_at else None
        accumulated = log.accumulated_seconds if log else 0

        # Calcular si la tarea está bloqueada por tiempo de inicio de turno
        unlock_time_iso = None
        if getattr(item, 'unlock_delay', None) and active_shift.actual_start_time:
            unlock_time = active_shift.actual_start_time + item.unlock_delay
            unlock_time_iso = unlock_time.isoformat()

        # CLAVE: Bandera para saber a qué columna del Frontend enviarla
        is_scheduled = item.specific_time is not None

        tasks_for_js.append({
            'id': item.id,
            'parent_id': getattr(item, 'parent_id', None),
            'description': item.description,
            'phase': item.phase,
            
            # Nuevos campos para la arquitectura de 2 columnas
            'is_scheduled': is_scheduled,
            'specific_time': item.specific_time.strftime('%H:%M') if is_scheduled else None,
            
            'completed': is_completed,
            'status': log.status if log else 'pending',
            'observation': log.observacion if log else '',
            'duration': duration_str,
            'started_at': started_at_iso,
            'accumulated': accumulated,
            'is_sequential': getattr(item, 'is_sequential', True),
            'unlock_time': unlock_time_iso,
        })

    # Nombres amigables para el título de la página
    phase_titles = {
        'start': 'Inicio de Turno', 
        'during': 'Durante el Turno', 
        'end': 'Finalización de Turno'
    }

    return render(request, 'operator/checklist_phase.html', {
        'tasks_for_js': tasks_for_js,
        'phase_name': phase_titles.get(phase),
        'phase': phase
    })


@require_POST
@login_required
def start_checklist_task(request, item_id):
    active_shift = get_active_shift(request.user)
    if not active_shift:
        return JsonResponse({'status': 'error', 'message': 'No hay turno activo.'}, status=403)

    try:
        item = ChecklistItem.objects.get(id=item_id)
        log, created = ChecklistLog.objects.get_or_create(
            operator_shift=active_shift, item=item,
            defaults={
                'status': 'in_progress', 'started_at': timezone.now(),
                'accumulated_seconds': 0, 'duration_seconds': 0, 'legal_agreement': False
            }
        )
        if log.status in ['pending', 'paused']:
            log.started_at = timezone.now()
            log.status = 'in_progress'
            log.save()
        return JsonResponse({
            'status': 'success',
            'start_time': log.started_at.isoformat() if log.started_at else timezone.now().isoformat()
        })
    except ChecklistItem.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Tarea no encontrada.'}, status=404)


@require_POST
@login_required
def pause_checklist_task(request, item_id):
    active_shift = get_active_shift(request.user)
    if not active_shift:
        return JsonResponse({'status': 'error', 'message': 'No hay turno activo.'}, status=403)

    try:
        log = ChecklistLog.objects.get(operator_shift=active_shift, item_id=item_id)
        if log.status == 'in_progress' and log.started_at:
            delta = timezone.now() - log.started_at
            log.accumulated_seconds += int(delta.total_seconds())
            log.status = 'paused'
            log.started_at = None
            log.save()
        return JsonResponse({'status': 'success', 'message': 'Tarea pausada correctamente.'})
    except ChecklistLog.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Log no encontrado.'}, status=404)


@require_POST
@login_required
def finish_checklist_task(request, item_id):
    active_shift = get_active_shift(request.user)
    if not active_shift:
        return JsonResponse({'status': 'error', 'message': 'No hay turno activo.'}, status=403)

    try:
        log = ChecklistLog.objects.get(operator_shift=active_shift, item_id=item_id)
        if log.status == 'completed':
            return JsonResponse({'status': 'error', 'message': 'La tarea ya fue completada.'}, status=400)

        log.completed_at = timezone.now()
        if log.status == 'in_progress' and log.started_at:
            delta = log.completed_at - log.started_at
            log.duration_seconds = log.accumulated_seconds + int(delta.total_seconds())
        else:
            log.duration_seconds = log.accumulated_seconds

        log.observacion = request.POST.get('observacion', '')
        if 'attachment' in request.FILES:
            log.attachment = request.FILES['attachment']

        legal_agreed = request.POST.get('legal_agreement') == 'true'
        if log.item.requires_legal_check and not legal_agreed:
            return JsonResponse({'status': 'error', 'message': 'Debe aceptar la Declaración Jurada.'}, status=400)

        log.legal_agreement = legal_agreed
        log.status = 'completed'
        log.save()

        TraceabilityLog.objects.create(
            user=request.user,
            action=f"Tarea finalizada ({log.get_duration_display()}): '{log.item.description}'"
        )

        return JsonResponse({
            'status': 'success',
            'duration': log.get_duration_display(),
            'message': 'Tarea firmada correctamente.'
        })
    except ChecklistLog.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Debe iniciar la tarea primero.'}, status=400)
