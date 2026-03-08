from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Case, When, Value, IntegerField, Q
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
    # Si no hay hora manual, usamos la hora real de creación de la bitácora
    if not log.manual_timestamp:
        return log.created_at

    shift = log.operator_shift
    
    # Si por alguna razón no hay turno activo, usamos la fecha de creación
    if not shift or not shift.actual_start_time:
        candidate_dt = datetime.combine(log.created_at.date(), log.manual_timestamp)
        return timezone.make_aware(candidate_dt)

    shift_start = shift.actual_start_time
    # Creamos una fecha candidata combinando la fecha de inicio del turno con la hora manual
    candidate_dt = timezone.make_aware(datetime.combine(shift_start.date(), log.manual_timestamp))

    # 1. Manejo de turnos nocturnos (ej. 20:00 a 08:00)
    if shift.shift_type.start_time > shift.shift_type.end_time:
        if log.manual_timestamp <= shift.shift_type.end_time:
            candidate_dt += timedelta(days=1)
    
    # 2. EL ARREGLO: Manejo del lapso de gracia ANTES del turno
    if candidate_dt < shift_start:
        diferencia = shift_start - candidate_dt
        # Si se registró hace MÁS de 25 minutos antes del turno, asumimos que es del día anterior
        if diferencia > timedelta(minutes=25):
            candidate_dt -= timedelta(days=1)
        # Si la diferencia es <= 25 minutos (ej. 08:17 para un turno de 08:30),
        # NO restamos un día, lo dejamos dentro del mismo día y ciclo.

    # 3. Verificación de seguridad: si por algún motivo la fecha calculada está en el futuro respecto a ahora
    if candidate_dt > timezone.now():
        candidate_dt -= timedelta(days=1)

    return candidate_dt

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
    
    # === SOLUCIÓN DE ORDEN ===
    # En lugar de usar base_items.order_by('phase', 'order'), forzamos el orden aquí:
    return base_items.alias(
        phase_order=Case(
            When(phase='start', then=Value(1)),
            When(phase='during', then=Value(2)),
            When(phase='end', then=Value(3)),
            output_field=IntegerField(),
        )
    ).order_by('phase_order', 'order')
