import csv
from datetime import datetime
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.http import HttpResponse
from ..models import TurnReport, GPSIncident
from .auth import is_supervisor


@login_required
@user_passes_test(is_supervisor)
def view_turn_reports(request):
    reports = TurnReport.objects.filter(is_signed=True)

    operator_id = request.GET.get('operator')
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    order_by = request.GET.get('order_by', '-end_time')

    if operator_id:
        reports = reports.filter(operator_id=operator_id)
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            reports = reports.filter(end_time__date__gte=start_date)
        except ValueError:
            pass
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            reports = reports.filter(end_time__date__lte=end_date)
        except ValueError:
            pass

    reports = reports.order_by(order_by)
    operators = User.objects.filter(is_superuser=False).order_by('username')

    context = {
        'reports': reports,
        'operators': operators,
        'selected_operator': operator_id,
        'selected_start_date': start_date_str,
        'selected_end_date': end_date_str,
        'selected_order_by': order_by,
    }
    return render(request, 'admin/turn_reports/list.html', context)


@login_required
@user_passes_test(is_supervisor)
def gps_admin_reports(request):
    incidents = GPSIncident.objects.all().order_by('-incident_timestamp')
    return render(request, 'admin/gps/reports.html', {'incidents': incidents})


@login_required
@user_passes_test(is_supervisor)
def export_gps_excel(request):
    incidents = GPSIncident.objects.filter(status='resolved').order_by('incident_timestamp')
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = 'attachment; filename="Registro_Alarmas_GPS.csv"'
    writer = csv.writer(response, delimiter=';')

    writer.writerow([
        'TIPO DE ALARMA', 'FECHA', 'HORA', 'NOMBRE DE CONDUCTOR',
        'PATENTE o N°ENAP', 'COORDENADAS', 'SALA DE CONTROL',
        'OPERADOR SALA DE CONTROL (ENAP)', 'HORA AVISO SALA DE CONTROL',
        'OPERADOR TORRE DE CONTROL (SELFING)', 'OBSERVACIONES'
    ])

    for inc in incidents:
        fecha = inc.incident_timestamp.strftime('%d-%m-%Y') if inc.incident_timestamp else 'S/I'
        hora = inc.incident_timestamp.strftime('%H:%M:%S') if inc.incident_timestamp else 'S/I'
        hora_aviso = inc.taken_at.strftime('%H:%M:%S') if inc.taken_at else 'S/I'
        coords = f"{inc.latitude}, {inc.longitude}" if inc.latitude and inc.longitude else 'Sin coordenadas'
        sector = inc.sector_assigned.name if inc.sector_assigned else 'No Asignado'
        op_selfing = inc.operator.get_full_name() or inc.operator.username if inc.operator else 'Desconocido'
        notas = inc.operator_notes.replace('\n', ' ').replace('\r', '') if inc.operator_notes else ''

        writer.writerow([
            inc.alert_type, fecha, hora, inc.driver_name or 'S/Info',
            f"{inc.license_plate} {inc.unit_id or ''}".strip(),
            coords, sector, inc.who_answered or 'N/A', hora_aviso, op_selfing, notas
        ])

    return response
