from collections import OrderedDict
from io import BytesIO
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import logout
from django.utils import timezone
from django.core.files.base import ContentFile
from django.template.loader import get_template
from xhtml2pdf import pisa
from ..models import Company, UpdateLog, ChecklistLog, VirtualRoundLog, RoundInstallationLog, TurnReport, TraceabilityLog
from ..utils import link_callback
from ._helpers import get_active_shift


@login_required
def end_turn_preview(request):
    active_shift = get_active_shift(request.user)
    if not active_shift or not active_shift.actual_start_time:
        messages.error(request, "No tienes un turno activo o iniciado.")
        return redirect('operator_dashboard')

    validation_errors = []
    total_rondas_requeridas = 7
    rondas_completadas = VirtualRoundLog.objects.filter(operator_shift=active_shift).count()
    if rondas_completadas < total_rondas_requeridas:
        validation_errors.append(f"Faltan {total_rondas_requeridas - rondas_completadas} rondas virtuales.")

    if active_shift.monitored_companies.exists():
        empresas_requeridas = active_shift.monitored_companies.filter(installations__isnull=False).distinct()
    else:
        empresas_requeridas = Company.objects.filter(installations__isnull=False).distinct()

    ids_empresas_con_log = UpdateLog.objects.filter(
        operator_shift=active_shift
    ).values_list('installation__company_id', flat=True).distinct()
    empresas_faltantes_bitacora = [c.name for c in empresas_requeridas if c.id not in ids_empresas_con_log]

    if empresas_faltantes_bitacora:
        validation_errors.append(f"Falta registrar en bitácora para: {', '.join(empresas_faltantes_bitacora)}.")

    if validation_errors:
        messages.error(request, "No puedes finalizar el turno. Tareas pendientes: " + " ".join(validation_errors))
        return redirect('operator_dashboard')

    end_time = timezone.now()
    duration_timedelta = end_time - active_shift.actual_start_time
    total_seconds = int(duration_timedelta.total_seconds())
    formatted_duration = f"{total_seconds // 3600}h {(total_seconds % 3600) // 60}m"

    completed_checklist_qs = ChecklistLog.objects.filter(
        operator_shift=active_shift
    ).select_related('item').order_by('completed_at')
    phase_order = ['start', 'during', 'end']
    phase_display_names = {
        'start': '🚀 INICIO DE TURNO',
        'during': '⏰ DURANTE EL TURNO',
        'end': '🏁 FINALIZACIÓN DE TURNO'
    }

    checklist_by_phase = OrderedDict()
    for phase_key in phase_order:
        logs_for_phase = completed_checklist_qs.filter(item__phase=phase_key)
        if logs_for_phase.exists():
            checklist_by_phase[phase_key] = {
                'display_name': phase_display_names.get(phase_key),
                'logs': logs_for_phase
            }

    updates_log = UpdateLog.objects.filter(
        operator_shift=active_shift
    ).select_related('installation__company').order_by(
        'installation__company__name', 'installation__name', 'created_at'
    )
    rondas_virtuales = VirtualRoundLog.objects.filter(
        operator_shift=active_shift
    ).prefetch_related(
        'installation_logs__installation__company'
    ).order_by('start_time')

    # Calcular tiempo entre rondas (tiempo de respuesta)
    rondas_list = list(rondas_virtuales)
    for i, ronda in enumerate(rondas_list):
        if i == 0:
            ronda.gap_seconds = None
        else:
            prev = rondas_list[i - 1]
            if prev.end_time and ronda.start_time:
                ronda.gap_seconds = int((ronda.start_time - prev.end_time).total_seconds())
            else:
                ronda.gap_seconds = None

    context = {
        'operator': request.user,
        'start_time': active_shift.actual_start_time,
        'end_time': end_time,
        'duration': formatted_duration,
        'current_time': timezone.now(),
        'checklist_by_phase': checklist_by_phase,
        'updates_log': updates_log,
        'rondas_virtuales': rondas_list,
    }

    template = get_template('operator/turn/pdf.html')
    html = template.render(context)
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html.encode("UTF-8")), result, link_callback=link_callback)

    if not pdf.err:
        report, created = TurnReport.objects.get_or_create(
            operator_shift=active_shift,
            defaults={'operator': request.user, 'start_time': active_shift.actual_start_time}
        )
        pdf_file = ContentFile(result.getvalue())
        report.pdf_report.save(
            f'reporte_turno_{request.user.username}_{timezone.now().strftime("%Y%m%d")}.pdf',
            pdf_file,
            save=True
        )
        return redirect('sign_turn_report', report_id=report.id)

    messages.error(request, f"Error al generar el PDF: {pdf.err}")
    return redirect('operator_dashboard')


@login_required
def sign_turn_report(request, report_id):
    report = get_object_or_404(TurnReport, id=report_id, operator=request.user)

    if request.method == 'POST':
        shift_to_close = report.operator_shift
        if shift_to_close:
            shift_to_close.actual_end_time = timezone.now()
            shift_to_close.save()

            report.is_signed = True
            report.signed_at = timezone.now()
            report.save()

            TraceabilityLog.objects.create(user=request.user, action="Firmó y finalizó su reporte de turno.")
            if request.user.is_authenticated:
                logout(request)

            messages.success(request, "Turno finalizado con éxito.")
            return redirect('login')
        else:
            messages.error(request, "Error: No se pudo encontrar el turno asociado a este reporte.")
            return redirect('operator_dashboard')

    return render(request, 'operator/turn/preview.html', {'report': report})
