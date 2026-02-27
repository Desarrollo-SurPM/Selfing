from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.contrib import messages
from django.utils import timezone
from ..models import VirtualRoundLog, RoundInstallationLog, Installation, TraceabilityLog
from ._helpers import get_active_shift


@login_required
def start_virtual_round(request):
    is_ajax = "application/json" in request.headers.get('Content-Type', '')

    if request.method == 'POST':
        active_shift = get_active_shift(request.user)

        if 'active_round_id' in request.session:
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': 'Ya hay una ronda virtual en curso.'}, status=400)
            messages.warning(request, 'Ya hay una ronda virtual en curso.')
            return redirect('operator_dashboard')

        if active_shift and active_shift.actual_start_time:
            new_round = VirtualRoundLog.objects.create(operator_shift=active_shift, start_time=timezone.now())
            request.session['active_round_id'] = new_round.id
            if is_ajax:
                return JsonResponse({'status': 'success', 'round_id': new_round.id})
            messages.success(request, 'Ronda virtual iniciada con éxito.')
            return redirect('operator_dashboard')

    message = 'No se pudo iniciar la ronda. No hay un turno activo.'
    if is_ajax:
        return JsonResponse({'status': 'error', 'message': message}, status=400)
    messages.error(request, message)
    return redirect('operator_dashboard')


@login_required
def virtual_round_view(request):
    active_shift = get_active_shift(request.user)
    if not active_shift:
        return redirect('operator_dashboard')

    active_round = VirtualRoundLog.objects.filter(
        operator_shift=active_shift, end_time__isnull=True
    ).order_by('-start_time').first()
    if not active_round:
        return redirect('operator_dashboard')

    if active_shift.monitored_companies.exists():
        allowed_installations = Installation.objects.filter(
            company__in=active_shift.monitored_companies.all()
        ).select_related('company').order_by('company__name', 'name')
    else:
        allowed_installations = Installation.objects.all().select_related('company').order_by('company__name', 'name')

    logs = RoundInstallationLog.objects.filter(virtual_round=active_round)
    logs_dict = {log.installation_id: log for log in logs}

    companies_dict = {}
    for inst in allowed_installations:
        comp_id = inst.company.id
        if comp_id not in companies_dict:
            companies_dict[comp_id] = {'id': comp_id, 'name': inst.company.name, 'installations': []}

        log = logs_dict.get(inst.id)
        companies_dict[comp_id]['installations'].append({
            'id': inst.id,
            'name': inst.name,
            'status': log.status if log else 'pending',
            'duration': log.get_duration_display() if log else '00:00',
            'started_at': log.start_time.isoformat() if log and log.start_time else None,
            'accumulated': log.accumulated_seconds if log else 0,
            'observation': log.observacion if log else '',
        })

    round_data_for_js = {'round_id': active_round.id, 'companies': list(companies_dict.values())}
    return render(request, 'operator/virtual_round/main.html', {'round_data': round_data_for_js})


@require_POST
@login_required
def start_round_installation(request, round_id, inst_id):
    active_round = get_object_or_404(VirtualRoundLog, id=round_id, operator_shift__operator=request.user)
    installation = get_object_or_404(Installation, id=inst_id)

    log, created = RoundInstallationLog.objects.get_or_create(
        virtual_round=active_round, installation=installation
    )
    log.status = 'in_progress'
    log.start_time = timezone.now()
    log.save()

    return JsonResponse({'status': 'success', 'start_time': log.start_time.isoformat()})


@require_POST
@login_required
def pause_round_installation(request, round_id, inst_id):
    active_round = get_object_or_404(VirtualRoundLog, id=round_id, operator_shift__operator=request.user)
    log = get_object_or_404(RoundInstallationLog, virtual_round=active_round, installation_id=inst_id)

    if log.status == 'in_progress' and log.start_time:
        delta = timezone.now() - log.start_time
        log.accumulated_seconds += int(delta.total_seconds())
        log.status = 'paused'
        log.start_time = None
        log.save()

    return JsonResponse({'status': 'success'})


@require_POST
@login_required
def finish_round_installation(request, round_id, inst_id):
    active_round = get_object_or_404(VirtualRoundLog, id=round_id, operator_shift__operator=request.user)
    log = get_object_or_404(RoundInstallationLog, virtual_round=active_round, installation_id=inst_id)

    if log.status == 'completed':
        return JsonResponse({'status': 'error', 'message': 'Ya revisada.'}, status=400)

    log.end_time = timezone.now()
    if log.status == 'in_progress' and log.start_time:
        delta = log.end_time - log.start_time
        log.duration_seconds = log.accumulated_seconds + int(delta.total_seconds())
    else:
        log.duration_seconds = log.accumulated_seconds

    log.status = 'completed'
    if 'attachment' in request.FILES:
        log.attachment = request.FILES['attachment']
    log.observacion = request.POST.get('observacion', '')
    log.save()

    return JsonResponse({'status': 'success', 'duration': log.get_duration_display()})


@require_POST
@login_required
def close_virtual_round(request, round_id):
    active_round = get_object_or_404(VirtualRoundLog, id=round_id, operator_shift__operator=request.user)

    if active_round.end_time:
        return JsonResponse({'status': 'error', 'message': 'La ronda ya fue finalizada.'}, status=400)

    end_time = timezone.now()
    duration = end_time - active_round.start_time
    active_round.end_time = end_time
    active_round.duration_seconds = duration.total_seconds()

    logs = RoundInstallationLog.objects.filter(
        virtual_round=active_round, end_time__isnull=False
    ).select_related('installation')
    active_round.checked_installations = ", ".join([log.installation.name for log in logs])
    active_round.save()

    if 'active_round_id' in request.session:
        del request.session['active_round_id']

    TraceabilityLog.objects.create(
        user=request.user,
        action=f"Finalizó ronda virtual completa. Duración total: {active_round.get_duration_display()}."
    )

    return JsonResponse({'status': 'success', 'message': 'Ronda finalizada correctamente.'})
