from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Q
from ..models import OperatorShift, ChecklistItem, Company, ChecklistLog


def get_active_shift(user):
    now = timezone.now()
    today = now.date()
    yesterday = today - timedelta(days=1)

    time_threshold = now - timedelta(hours=18)
    active_shift = OperatorShift.objects.select_related('shift_type', 'operator').filter(
        operator=user,
        actual_start_time__gte=time_threshold,
        actual_end_time__isnull=True
    ).order_by('-actual_start_time').first()

    if active_shift:
        return active_shift

    pending_shift = OperatorShift.objects.select_related('shift_type', 'operator').filter(
        operator=user,
        date__in=[today, yesterday],
        actual_start_time__isnull=True,
        actual_end_time__isnull=True
    ).order_by('-date', 'shift_type__start_time').first()

    return pending_shift


def get_operator_companies(operator_user):
    active_shift = get_active_shift(operator_user)
    if not active_shift:
        return Company.objects.none()
    if active_shift.monitored_companies.exists():
        return active_shift.monitored_companies.all()
    return Company.objects.all()


def calculate_log_datetime(log):
    if log.manual_timestamp:
        event_time = log.manual_timestamp
    else:
        event_time = timezone.localtime(log.created_at).time()

    shift = log.operator_shift
    base_date = shift.date
    start = shift.shift_type.start_time
    end = shift.shift_type.end_time

    if start > end:
        if event_time <= end:
            return datetime.combine(base_date + timedelta(days=1), event_time)
        elif event_time >= start:
            return datetime.combine(base_date, event_time)
        else:
            if event_time.hour >= 12:
                return datetime.combine(base_date, event_time)
            else:
                return datetime.combine(base_date + timedelta(days=1), event_time)
    else:
        if start.hour < 6:
            if event_time.hour >= 20:
                return datetime.combine(base_date - timedelta(days=1), event_time)
            return datetime.combine(base_date, event_time)
        else:
            if event_time < start and event_time.hour < 12:
                return datetime.combine(base_date + timedelta(days=1), event_time)
            return datetime.combine(base_date, event_time)


def get_applicable_checklist_items(active_shift):
    if not active_shift or not active_shift.shift_type:
        return ChecklistItem.objects.none()
    today_weekday = timezone.now().weekday()
    current_shift_type = active_shift.shift_type

    turnos_filter = Q(turnos_aplicables=current_shift_type) | Q(turnos_aplicables__isnull=True)
    dias_filter = Q(dias_aplicables__contains=str(today_weekday)) | Q(dias_aplicables__isnull=True) | Q(dias_aplicables='')

    base_items = ChecklistItem.objects.filter(turnos_filter, dias_filter).distinct()
    if active_shift.monitored_companies.exists():
        assigned_companies = active_shift.monitored_companies.all()
        base_items = base_items.filter(Q(company__isnull=True) | Q(company__in=assigned_companies))
    return base_items.order_by('phase', 'order')
