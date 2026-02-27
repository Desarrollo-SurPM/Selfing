import json
from datetime import time, timedelta
from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from django.db.models import Avg, Count
from django.db.models.functions import ExtractHour
from ..models import (
    UpdateLog, TurnReport, OperatorShift, MonitoredService,
    TraceabilityLog, VirtualRoundLog, ChecklistLog, GPSIncident
)
from .auth import is_supervisor


@login_required
@user_passes_test(is_supervisor)
def admin_dashboard(request):
    ahora = timezone.now()

    today_at_8_30 = ahora.replace(hour=8, minute=30, second=0, microsecond=0)
    if ahora.time() < time(8, 30):
        start_of_operational_day = today_at_8_30 - timedelta(days=1)
    else:
        start_of_operational_day = today_at_8_30

    start_of_today = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_week = ahora - timedelta(days=7)
    start_of_month = ahora - timedelta(days=30)

    novedades_hoy = UpdateLog.objects.filter(created_at__gte=start_of_operational_day).count()
    reportes_finalizados_count = TurnReport.objects.filter(is_signed=True, signed_at__gte=start_of_operational_day).count()
    operadores_en_turno = OperatorShift.objects.filter(actual_start_time__isnull=False, actual_end_time__isnull=True).count()
    servicios_monitoreados_activos = MonitoredService.objects.filter(is_active=True).count()

    traceability_logs = TraceabilityLog.objects.select_related('user').all().order_by('-timestamp')[:8]
    reports = UpdateLog.objects.filter(created_at__gte=start_of_operational_day).select_related(
        'operator_shift__operator', 'installation__company'
    ).order_by('-created_at')

    round_stats = VirtualRoundLog.objects.filter(
        start_time__gte=start_of_month,
        duration_seconds__isnull=False,
        duration_seconds__lt=7200
    ).values('operator_shift__operator__username').annotate(
        avg_duration=Avg('duration_seconds')
    ).order_by('avg_duration')

    r_labels = [x['operator_shift__operator__username'] for x in round_stats]
    r_data = [round((x['avg_duration'] or 0) / 60, 1) for x in round_stats]
    global_round_avg = round(sum(r_data) / len(r_data), 1) if r_data else 0

    chk_stats = ChecklistLog.objects.filter(
        status='completed',
        duration_seconds__isnull=False,
        duration_seconds__lt=3600
    ).values('item__phase').annotate(avg_duration=Avg('duration_seconds'))

    chk_phases_dict = {'start': 'Inicio Turno', 'during': 'Durante Turno', 'end': 'Cierre Turno'}
    c_labels = [chk_phases_dict.get(x['item__phase'], x['item__phase']) for x in chk_stats]
    c_data = [round((x['avg_duration'] or 0) / 60, 1) for x in chk_stats]

    gps_stats = GPSIncident.objects.filter(
        resolved_at__gte=start_of_month,
        response_time_seconds__isnull=False
    ).aggregate(avg_time=Avg('response_time_seconds'))
    avg_gps_response = round((gps_stats['avg_time'] or 0) / 60, 1)

    def get_hourly_pattern(start_date):
        qs = UpdateLog.objects.filter(created_at__gte=start_date).annotate(
            hour=ExtractHour('created_at')
        ).values('hour').annotate(count=Count('id')).order_by('hour')
        data_dict = {x['hour']: x['count'] for x in qs}
        return [data_dict.get(h, 0) for h in range(24)]

    pattern_today = get_hourly_pattern(start_of_today)
    pattern_week = get_hourly_pattern(start_of_week)
    pattern_month = get_hourly_pattern(start_of_month)
    hours_labels = [f"{h:02d}:00" for h in range(24)]

    company_stats = UpdateLog.objects.filter(created_at__gte=start_of_month).values(
        'installation__company__name'
    ).annotate(total=Count('id')).order_by('-total')[:5]

    context = {
        'novedades_hoy': novedades_hoy,
        'reportes_finalizados_count': reportes_finalizados_count,
        'operadores_en_turno': operadores_en_turno,
        'servicios_monitoreados_activos': servicios_monitoreados_activos,
        'reports': reports,
        'traceability_logs': traceability_logs,
        'chart_rounds_labels': json.dumps(r_labels),
        'chart_rounds_data': json.dumps(r_data),
        'global_round_avg': global_round_avg,
        'chart_chk_labels': json.dumps(c_labels),
        'chart_chk_data': json.dumps(c_data),
        'avg_gps_response': avg_gps_response,
        'chart_rhythm_labels': json.dumps(hours_labels),
        'chart_rhythm_today': json.dumps(pattern_today),
        'chart_rhythm_week': json.dumps(pattern_week),
        'chart_rhythm_month': json.dumps(pattern_month),
        'chart_comp_labels': json.dumps([x['installation__company__name'] for x in company_stats]),
        'chart_comp_data': json.dumps([x['total'] for x in company_stats]),
    }
    return render(request, 'admin/dashboard.html', context)
