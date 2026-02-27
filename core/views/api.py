import json
from datetime import timedelta
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from ..models import Installation, MonitoredService, UpdateLog, OperatorShift, VirtualRoundLog
from ._helpers import get_active_shift, get_applicable_checklist_items
from .auth import is_supervisor


@login_required
def ajax_get_installations_for_company(request, company_id):
    installations = Installation.objects.filter(company_id=company_id).order_by('name')
    data = [{'id': inst.id, 'name': inst.name} for inst in installations]
    return JsonResponse({'installations': data})


@login_required
def get_updates_for_company(request, company_id):
    active_shift = get_active_shift(request.user)
    if not active_shift:
        return JsonResponse({'grouped_updates': []})

    installations_with_updates = Installation.objects.filter(
        company_id=company_id,
        updatelog__operator_shift=active_shift
    ).distinct()
    response_data = []
    for installation in installations_with_updates:
        updates = UpdateLog.objects.filter(
            installation=installation, operator_shift=active_shift
        ).order_by('-created_at')
        updates_list = [
            {'id': u.id, 'text': f"{u.created_at.strftime('%d/%m %H:%M')} - {u.message}"}
            for u in updates
        ]
        response_data.append({'installation_name': installation.name, 'updates': updates_list})

    return JsonResponse({'grouped_updates': response_data})


@login_required
def get_service_status(request):
    services = MonitoredService.objects.filter(is_active=True)
    status_list = []
    for s in services:
        latest_log = s.logs.order_by('-timestamp').first()
        status_list.append({
            'id': s.id,
            'name': s.name,
            'status': latest_log.is_up if latest_log else None
        })
    from django.shortcuts import render
    return render(request, 'partials/_service_status_panel.html', {'service_status_list': status_list})


@login_required
def check_pending_alarms(request):
    active_shift = get_active_shift(request.user)
    overdue_tasks = []

    if active_shift and active_shift.actual_start_time:
        now = timezone.now()
        applicable_items = get_applicable_checklist_items(active_shift)
        from ..models import ChecklistLog
        completed_item_ids = ChecklistLog.objects.filter(
            operator_shift=active_shift
        ).values_list('item_id', flat=True)

        pending_items_with_alarm = applicable_items.exclude(id__in=completed_item_ids).filter(
            alarm_trigger_delay__isnull=False,
            alarm_trigger_delay__gt=timedelta(seconds=0)
        )

        for item in pending_items_with_alarm:
            due_time = active_shift.actual_start_time + item.alarm_trigger_delay
            if now > due_time:
                overdue_tasks.append({'description': item.description})

    return JsonResponse({'overdue_tasks': overdue_tasks})


@login_required
def check_first_round_started(request):
    active_shift = get_active_shift(request.user)
    has_rounds = VirtualRoundLog.objects.filter(operator_shift=active_shift).exists() if active_shift else False
    return JsonResponse({'has_rounds': has_rounds})


@login_required
@user_passes_test(is_supervisor)
@csrf_exempt
@transaction.atomic
def api_save_shift_batch(request):
    if request.method == 'POST':
        try:
            payload = json.loads(request.body)
            changes = payload.get('changes', [])
            updated_count = deleted_count = 0

            for item in changes:
                operator_id = item.get('operator_id')
                date_str = item.get('date')
                shift_type_id = item.get('shift_type_id')
                company_ids = item.get('company_ids')

                if not operator_id or not date_str:
                    continue

                if shift_type_id:
                    shift, created = OperatorShift.objects.update_or_create(
                        operator_id=operator_id,
                        date=date_str,
                        defaults={'shift_type_id': shift_type_id}
                    )
                    if company_ids is not None:
                        shift.monitored_companies.set(company_ids)
                    updated_count += 1
                else:
                    OperatorShift.objects.filter(operator_id=operator_id, date=date_str).delete()
                    deleted_count += 1

            return JsonResponse({
                'status': 'success',
                'message': f'Guardados {updated_count}, eliminados {deleted_count}.'
            })
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    return JsonResponse({'status': 'error'}, status=405)
