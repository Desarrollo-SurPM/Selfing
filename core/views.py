# desarrollo-surpm/selfing/Selfing-mejorasorden/core/views.py
from django.db.models import Min, Max
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.template.loader import get_template
from xhtml2pdf import pisa
from django.views.decorators.http import require_POST
from .utils import link_callback
from django.core.mail import send_mail
from .models import GPSIncident
import csv
from django.template.loader import render_to_string
from django.db.models import (
    Q, Min, Max, Count, TimeField, Case, When, DateTimeField, F, Value, ExpressionWrapper, DateField, Avg
)
from collections import defaultdict
from django.contrib import messages
from django.db.models.functions import ExtractHour, ExtractWeekDay, ExtractMonth
import calendar
from io import BytesIO
from django.db import transaction
from django.core.files.base import ContentFile
from django import forms
from datetime import date, timedelta, datetime, time
from collections import defaultdict
from django.contrib.auth import logout
from collections import OrderedDict
import json
from .forms import GPSNotificationSettingsForm
from django.views.decorators.csrf import csrf_exempt 
import re 
from django.db.models.functions import Coalesce, Cast
from django.core.mail import EmailMultiAlternatives 
import mimetypes 
from django.utils.html import strip_tags
from django.conf import settings
from django.core.mail import get_connection

from .models import (
    Company, Installation, OperatorProfile, ShiftType, OperatorShift,
    ChecklistItem, ChecklistLog, VirtualRoundLog, UpdateLog, Email, EmergencyContact,
    TurnReport, MonitoredService, ServiceStatusLog, TraceabilityLog, ShiftNote,
    Vehicle, VehiclePosition, VehicleAlert, VehicleRoute, GPSNotificationSettings, RoundInstallationLog
)
from .forms import (
    UpdateLogForm, OperatorCreationForm, ShiftNoteForm,
    OperatorChangeForm, CompanyForm, InstallationForm, ChecklistItemForm, EmergencyContactForm,
    MonitoredServiceForm, ShiftTypeForm, OperatorShiftForm, VirtualRoundCompletionForm, UpdateLogEditForm, AdminUpdateLogForm
)

def is_supervisor(user):
    return user.is_superuser

@login_required
def home(request):
    if is_supervisor(request.user):
        return redirect('admin_dashboard')
    else:
        return redirect('operator_dashboard')

# --- VISTAS DE ADMINISTRADOR ---
@login_required
@user_passes_test(is_supervisor)
def admin_dashboard(request):
    ahora = timezone.now()
    
    # Cálculos de rangos de fechas
    today_at_8_30 = ahora.replace(hour=8, minute=30, second=0, microsecond=0)
    if ahora.time() < time(8, 30):
        start_of_operational_day = today_at_8_30 - timedelta(days=1)
    else:
        start_of_operational_day = today_at_8_30
    
    start_of_today = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_week = ahora - timedelta(days=7)   
    start_of_month = ahora - timedelta(days=30) 

    # KPIs Superiores
    novedades_hoy = UpdateLog.objects.filter(created_at__gte=start_of_operational_day).count()
    reportes_finalizados_count = TurnReport.objects.filter(is_signed=True, signed_at__gte=start_of_operational_day).count()
    operadores_en_turno = OperatorShift.objects.filter(actual_start_time__isnull=False, actual_end_time__isnull=True).count()
    servicios_monitoreados_activos = MonitoredService.objects.filter(is_active=True).count()
    
    traceability_logs = TraceabilityLog.objects.select_related('user').all().order_by('-timestamp')[:8]
    reports = UpdateLog.objects.filter(created_at__gte=start_of_operational_day).select_related(
        'operator_shift__operator', 'installation__company'
    ).order_by('-created_at')
    
    # ==========================================
    # DATOS PARA INTELIGENCIA DE NEGOCIOS (BI)
    # ==========================================

    # 1. TIEMPO MEDIO DE RONDAS POR OPERADOR
    round_stats = VirtualRoundLog.objects.filter(
        start_time__gte=start_of_month,
        duration_seconds__isnull=False,
        duration_seconds__lt=7200 # Ignorar outliers de más de 2 horas
    ).values('operator_shift__operator__username').annotate(
        avg_duration=Avg('duration_seconds')
    ).order_by('avg_duration')

    r_labels = [x['operator_shift__operator__username'] for x in round_stats]
    r_data = [round((x['avg_duration'] or 0) / 60, 1) for x in round_stats]
    global_round_avg = round(sum(r_data) / len(r_data), 1) if r_data else 0

    # 2. RENDIMIENTO CHECKLIST (Tiempo promedio por Fase)
    chk_stats = ChecklistLog.objects.filter(
        status='completed',
        duration_seconds__isnull=False,
        duration_seconds__lt=3600
    ).values('item__phase').annotate(
        avg_duration=Avg('duration_seconds')
    )
    
    chk_phases_dict = {'start': 'Inicio Turno', 'during': 'Durante Turno', 'end': 'Cierre Turno'}
    c_labels = [chk_phases_dict.get(x['item__phase'], x['item__phase']) for x in chk_stats]
    c_data = [round((x['avg_duration'] or 0) / 60, 1) for x in chk_stats]

    # 3. TIEMPO DE RESPUESTA GPS (Minutos)
    gps_stats = GPSIncident.objects.filter(
        resolved_at__gte=start_of_month,
        response_time_seconds__isnull=False
    ).aggregate(avg_time=Avg('response_time_seconds'))
    avg_gps_response = round((gps_stats['avg_time'] or 0) / 60, 1)

    # 4. RITMO DE NOVEDADES (DENSIDAD)
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

    # 5. CARGA POR EMPRESA
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
        # Variables BI
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
    return render(request, 'admin_dashboard.html', context)

import os

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

@login_required
@user_passes_test(lambda u: u.is_superuser)
def review_and_send_novedades(request):
    CUTOFF_TIME = time(8, 30)
    ahora = timezone.now()
    today_at_cutoff = ahora.replace(hour=CUTOFF_TIME.hour, minute=CUTOFF_TIME.minute, second=0, microsecond=0)

    if ahora.time() < CUTOFF_TIME:
        end_of_cycle = today_at_cutoff - timedelta(days=1)
    else:
        end_of_cycle = today_at_cutoff
    
    start_of_cycle = end_of_cycle - timedelta(days=1)

    cycle_shifts_qs = OperatorShift.objects.filter(
        actual_start_time__gte=start_of_cycle,
        actual_start_time__lt=end_of_cycle
    ).select_related('operator', 'shift_type').order_by('actual_start_time')

    if not cycle_shifts_qs.exists():
        messages.info(request, "Aún no ha finalizado un ciclo de turnos para generar un reporte.")
        return render(request, 'review_and_send.html', {
            'companies': None, 
            'add_novedad_form': AdminUpdateLogForm(cycle_shifts=cycle_shifts_qs)
        })

    next_shift_after_cycle = OperatorShift.objects.filter(actual_start_time__gte=end_of_cycle).first()
    if next_shift_after_cycle and next_shift_after_cycle.actual_end_time is not None:
        messages.info(request, "El periodo para enviar el reporte del ciclo anterior ha finalizado.")
        return render(request, 'review_and_send.html', {
            'companies': None, 
            'add_novedad_form': AdminUpdateLogForm(cycle_shifts=OperatorShift.objects.none())
        })
    
    form_to_render = None

    if request.method == 'POST':
        if 'action' in request.POST and request.POST['action'] == 'add_novedad':
            form = AdminUpdateLogForm(request.POST, request.FILES, cycle_shifts=cycle_shifts_qs)
            if form.is_valid():
                selected_shift = form.cleaned_data.get('target_shift')
                if selected_shift and cycle_shifts_qs.filter(pk=selected_shift.pk).exists():
                    new_log = form.save(commit=False)
                    new_log.operator_shift = selected_shift
                    new_log.save()
                    messages.success(request, f'Novedad agregada al turno de {selected_shift.operator.username}.')
                else:
                    messages.error(request, 'El turno seleccionado no es válido.')
                
                company_id_redirect = request.POST.get('company_id_for_redirect', '')
                if company_id_redirect:
                    return redirect(f"{request.path}?company_id={company_id_redirect}")
                return redirect('review_and_send_novedades')
            else:
                messages.error(request, 'Error al agregar la novedad.')
                form_to_render = form
        
        elif 'confirm_send' in request.POST:
            company_id_form = request.POST.get('company_id')
            company = get_object_or_404(Company, id=company_id_form)
            selected_ids = request.POST.getlist('updates_to_send')
            observations = request.POST.get('observations', '')

            with transaction.atomic():
                 for update_id in selected_ids:
                    new_message = request.POST.get(f'message_{update_id}')
                    if new_message is not None:
                        try:
                            log_to = UpdateLog.objects.get(id=update_id)
                            if log_to.message != new_message:
                                if not log_to.original_message and not log_to.is_edited:
                                     log_to.original_message = log_to.message
                                log_to.message = new_message
                                log_to.is_edited = True
                                log_to.edited_at = timezone.now()
                                log_to.save()
                        except UpdateLog.DoesNotExist:
                            continue

            updates_qs = UpdateLog.objects.filter(id__in=selected_ids).select_related(
                'operator_shift__shift_type', 'installation', 'operator_shift'
            )
            updates_list = list(updates_qs)
            updates_list.sort(key=lambda x: (x.installation.name, calculate_log_datetime(x)))

            email_string = company.email or ""
            recipient_list = [email.strip() for email in email_string.split(',') if email.strip()]

            if recipient_list:
                try:
                    protocol = 'https' if request.is_secure() else 'http'
                    domain = request.get_host()
                    base_url = f"{protocol}://{domain}"
                    
                    email_context = {
                        'company': company,
                        'updates': updates_list, 
                        'observations': observations,
                        'enviado_por': request.user,
                        'cycle_start': start_of_cycle,
                        'cycle_end': end_of_cycle,
                        'base_url': base_url,
                    }
                    
                    html_content = render_to_string('emails/reporte_novedades.html', email_context)
                    subject = f"Reporte de Novedades - {company.name} - {end_of_cycle.strftime('%d/%m/%Y')}"
                    
                    msg = EmailMultiAlternatives(subject, "Reporte HTML", None, recipient_list)
                    msg.attach_alternative(html_content, "text/html")

                    count_imgs = 0
                    for update in updates_list:
                        if update.attachment and os.path.exists(update.attachment.path):
                            try:
                                msg.attach_file(update.attachment.path)
                                count_imgs += 1
                            except Exception:
                                pass

                    msg.send()
                    
                    UpdateLog.objects.filter(id__in=selected_ids).update(is_sent=True)
                    TraceabilityLog.objects.create(user=request.user, action=f"Envió correo a {company.name} ({count_imgs} imgs).")
                    messages.success(request, f"Correo enviado a {company.name}.")
                except Exception as e:
                    messages.error(request, f"Error al enviar: {e}")
            else:
                messages.warning(request, f"{company.name} no tiene correo.")

            return redirect('review_and_send_novedades')

    if form_to_render is None:
        form_to_render = AdminUpdateLogForm(cycle_shifts=cycle_shifts_qs)

    company_id = request.GET.get('company_id')
    selected_company = None
    novedades_pendientes = None 
    
    base_qs = UpdateLog.objects.filter(
        is_sent=False,
        operator_shift__in=cycle_shifts_qs
    ).select_related('installation__company', 'operator_shift__shift_type', 'operator_shift')

    company_ids = base_qs.values_list('installation__company_id', flat=True).distinct()
    companies_with_pending_updates = Company.objects.filter(id__in=company_ids).order_by('name')

    if company_id:
        try:
            selected_company = companies_with_pending_updates.get(id=int(company_id))
            raw_updates = list(base_qs.filter(installation__company=selected_company))
            raw_updates.sort(key=lambda x: (x.installation.name, calculate_log_datetime(x)))
            novedades_pendientes = raw_updates
        except (Company.DoesNotExist, ValueError):
            selected_company = None

    context = {
        'companies': companies_with_pending_updates,
        'selected_company': selected_company,
        'novedades_pendientes': novedades_pendientes,
        'cycle_end': end_of_cycle,
        'start_of_cycle': start_of_cycle,
        'add_novedad_form': form_to_render,
    }
    return render(request, 'review_and_send.html', context)

@login_required
def ajax_get_installations_for_company(request, company_id):
    installations = Installation.objects.filter(company_id=company_id).order_by('name')
    data = [{'id': inst.id, 'name': inst.name} for inst in installations]
    return JsonResponse({'installations': data})

@login_required
@user_passes_test(is_supervisor)
def manage_operators(request):
    operators = User.objects.filter(is_superuser=False)
    return render(request, 'manage_operators.html', {'operators': operators})

@login_required
@user_passes_test(is_supervisor)
def create_operator(request):
    if request.method == 'POST':
        form = OperatorCreationForm(request.POST)
        if form.is_valid(): form.save(); return redirect('manage_operators')
    else: form = OperatorCreationForm()
    return render(request, 'operator_form.html', {'form': form, 'title': 'Añadir Operador'})

@login_required
@user_passes_test(is_supervisor)
def edit_operator(request, user_id):
    op = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        form = OperatorChangeForm(request.POST, instance=op)
        if form.is_valid(): form.save(); return redirect('manage_operators')
    else: form = OperatorChangeForm(instance=op)
    return render(request, 'operator_form.html', {'form': form, 'title': 'Editar Operador'})

@login_required
@user_passes_test(is_supervisor)
def delete_operator(request, user_id):
    op = get_object_or_404(User, id=user_id)
    if request.method == 'POST': op.delete(); return redirect('manage_operators')
    return render(request, 'operator_confirm_delete.html', {'operator': op})

@login_required
@user_passes_test(is_supervisor)
def manage_companies(request):
    companies = Company.objects.all()
    total_installations = Installation.objects.count()
    context = {'companies': companies, 'total_installations': total_installations}
    return render(request, 'manage_companies.html', context)

@login_required
@user_passes_test(is_supervisor)
def create_company(request):
    if request.method == 'POST':
        form = CompanyForm(request.POST)
        if form.is_valid(): form.save(); return redirect('manage_companies')
    else: form = CompanyForm()
    return render(request, 'company_form.html', {'form': form, 'title': 'Añadir Empresa'})

@login_required
@user_passes_test(is_supervisor)
def edit_company(request, company_id):
    company = get_object_or_404(Company, id=company_id)
    if request.method == 'POST':
        form = CompanyForm(request.POST, instance=company)
        if form.is_valid(): form.save(); return redirect('manage_companies')
    else: form = CompanyForm(instance=company)
    return render(request, 'company_form.html', {'form': form, 'title': 'Editar Empresa'})

@login_required
@user_passes_test(is_supervisor)
def delete_company(request, company_id):
    company = get_object_or_404(Company, id=company_id)
    if request.method == 'POST': company.delete(); return redirect('manage_companies')
    return render(request, 'company_confirm_delete.html', {'company': company})

@login_required
@user_passes_test(is_supervisor)
def manage_installations(request, company_id):
    company = get_object_or_404(Company, id=company_id)
    installations = Installation.objects.filter(company=company)
    return render(request, 'manage_installations.html', {'company': company, 'installations': installations})

@login_required
@user_passes_test(is_supervisor)
def create_installation(request, company_id):
    company = get_object_or_404(Company, id=company_id)
    if request.method == 'POST':
        form = InstallationForm(request.POST)
        if form.is_valid():
            inst = form.save(commit=False); inst.company = company; inst.save()
            return redirect('manage_installations', company_id=company.id)
    else:
        form = InstallationForm(initial={'company': company}); form.fields['company'].widget = forms.HiddenInput()
    return render(request, 'installation_form.html', {'form': form, 'title': f'Añadir Instalación para {company.name}', 'company': company})

@login_required
@user_passes_test(is_supervisor)
def edit_installation(request, installation_id):
    inst = get_object_or_404(Installation, id=installation_id)
    if request.method == 'POST':
        form = InstallationForm(request.POST, instance=inst)
        if form.is_valid(): form.save(); return redirect('manage_installations', company_id=inst.company.id)
    else:
        form = InstallationForm(instance=inst); form.fields['company'].widget = forms.HiddenInput()
    return render(request, 'installation_form.html', {'form': form, 'title': f'Editar Instalación {inst.name}', 'company': inst.company})

@login_required
@user_passes_test(is_supervisor)
def delete_installation(request, installation_id):
    inst = get_object_or_404(Installation, id=installation_id)
    company_id = inst.company.id
    if request.method == 'POST': inst.delete(); return redirect('manage_installations', company_id=company_id)
    return render(request, 'installation_confirm_delete.html', {'installation': inst})

@login_required
@user_passes_test(is_supervisor)
def manage_checklist_items(request):
    items = ChecklistItem.objects.all()
    return render(request, 'manage_checklist.html', {'items': items})

@login_required
@user_passes_test(is_supervisor)
def create_checklist_item(request):
    if request.method == 'POST':
        form = ChecklistItemForm(request.POST)
        if form.is_valid(): form.save(); return redirect('manage_checklist_items')
    else: form = ChecklistItemForm()
    return render(request, 'checklist_item_form.html', {'form': form, 'title': 'Añadir Tarea al Checklist'})

@login_required
@user_passes_test(is_supervisor)
def edit_checklist_item(request, item_id):
    item = get_object_or_404(ChecklistItem, id=item_id)
    if request.method == 'POST':
        form = ChecklistItemForm(request.POST, instance=item)
        if form.is_valid(): form.save(); return redirect('manage_checklist_items')
    else: form = ChecklistItemForm(instance=item)
    return render(request, 'checklist_item_form.html', {'form': form, 'title': 'Editar Tarea del Checklist'})

@login_required
@user_passes_test(is_supervisor)
def delete_checklist_item(request, item_id):
    item = get_object_or_404(ChecklistItem, id=item_id)
    if request.method == 'POST': item.delete(); return redirect('manage_checklist_items')
    return render(request, 'checklist_item_confirm_delete.html', {'item': item})

@login_required
@user_passes_test(is_supervisor)
def manage_monitored_services(request):
    services = MonitoredService.objects.all()
    return render(request, 'manage_monitored_services.html', {'services': services})

@login_required
@user_passes_test(is_supervisor)
def create_monitored_service(request):
    if request.method == 'POST':
        form = MonitoredServiceForm(request.POST)
        if form.is_valid(): form.save(); return redirect('manage_monitored_services')
    else: form = MonitoredServiceForm()
    return render(request, 'monitored_service_form.html', {'form': form, 'title': 'Añadir Servicio a Monitorear'})

@login_required
@user_passes_test(is_supervisor)
def edit_monitored_service(request, service_id):
    service = get_object_or_404(MonitoredService, id=service_id)
    if request.method == 'POST':
        form = MonitoredServiceForm(request.POST, instance=service)
        if form.is_valid(): form.save(); return redirect('manage_monitored_services')
    else: form = MonitoredServiceForm(instance=service)
    return render(request, 'monitored_service_form.html', {'form': form, 'title': 'Editar Servicio Monitoreado'})

@login_required
@user_passes_test(is_supervisor)
def delete_monitored_service(request, service_id):
    service = get_object_or_404(MonitoredService, id=service_id)
    if request.method == 'POST': service.delete(); return redirect('manage_monitored_services')
    return render(request, 'monitored_service_confirm_delete.html', {'service': service})

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
        except ValueError: pass
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            reports = reports.filter(end_time__date__lte=end_date)
        except ValueError: pass

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
    return render(request, 'view_turn_reports.html', context)

@login_required
@user_passes_test(is_supervisor)
def manage_shifts(request):
    today = timezone.now().date()
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    search_query = request.GET.get('q', '')

    if start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            start_date = today.replace(day=1)
            end_date = (start_date + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    else:
        start_date = today.replace(day=1)
        _, last_day = calendar.monthrange(today.year, today.month)
        end_date = today.replace(day=last_day)

    delta = end_date - start_date
    days_range = [start_date + timedelta(days=i) for i in range(delta.days + 1)]

    operators = User.objects.filter(is_superuser=False).order_by('first_name', 'last_name')
    if search_query:
        operators = operators.filter(
            Q(first_name__icontains=search_query) | 
            Q(last_name__icontains=search_query) | 
            Q(username__icontains=search_query)
        )

    shift_types = ShiftType.objects.all()
    all_companies = Company.objects.all().order_by('name')

    existing_shifts = OperatorShift.objects.filter(
        date__range=[start_date, end_date],
        operator__in=operators
    ).select_related('shift_type').prefetch_related('monitored_companies')

    assignments = {}
    for shift in existing_shifts:
        assignments[(shift.operator_id, shift.date.strftime('%Y-%m-%d'))] = shift

    matrix_rows = []
    for operator in operators:
        row_data = {'operator': operator, 'days': []}
        for day in days_range:
            day_str = day.strftime('%Y-%m-%d')
            shift = assignments.get((operator.id, day_str))
            
            assigned_company_ids = []
            if shift:
                assigned_company_ids = list(shift.monitored_companies.values_list('id', flat=True))

            row_data['days'].append({
                'date': day_str,
                'shift': shift,
                'company_ids': assigned_company_ids
            })
        matrix_rows.append(row_data)

    context = {
        'current_start_date': start_date.strftime('%Y-%m-%d'),
        'current_end_date': end_date.strftime('%Y-%m-%d'),
        'search_query': search_query,
        'days_range': days_range,
        'matrix_rows': matrix_rows,
        'shift_types': shift_types,
        'all_companies': all_companies,
    }
    return render(request, 'manage_shifts.html', context)

@login_required
@user_passes_test(is_supervisor)
@csrf_exempt
def api_update_shift(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            operator_id = data.get('operator_id')
            date_str = data.get('date')
            shift_type_id = data.get('shift_type_id')
            company_ids = data.get('company_ids') 

            if not operator_id or not date_str:
                return JsonResponse({'status': 'error', 'message': 'Datos incompletos'}, status=400)

            if shift_type_id:
                shift, created = OperatorShift.objects.update_or_create(
                    operator_id=operator_id,
                    date=date_str,
                    defaults={'shift_type_id': shift_type_id}
                )
                if company_ids is not None:
                    shift.monitored_companies.set(company_ids)
                action = "updated"
            else:
                OperatorShift.objects.filter(operator_id=operator_id, date=date_str).delete()
                action = "deleted"

            return JsonResponse({'status': 'success', 'action': action})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    return JsonResponse({'status': 'error'}, status=405)

@login_required
@user_passes_test(is_supervisor)
def assign_shift(request):
    if request.method == 'POST':
        form = OperatorShiftForm(request.POST)
        if form.is_valid(): form.save(); return redirect('manage_shifts')
    else:
        form = OperatorShiftForm()
        form.fields['operator'].queryset = User.objects.filter(is_superuser=False)
    return render(request, 'assign_shift_form.html', {'form': form, 'title': 'Asignar Nuevo Turno'})

@login_required
@user_passes_test(is_supervisor)
def edit_assigned_shift(request, shift_id):
    shift = get_object_or_404(OperatorShift, id=shift_id)
    if request.method == 'POST':
        form = OperatorShiftForm(request.POST, instance=shift)
        if form.is_valid(): form.save(); return redirect('manage_shifts')
    else:
        form = OperatorShiftForm(instance=shift)
        form.fields['operator'].queryset = User.objects.filter(is_superuser=False)
    return render(request, 'assign_shift_form.html', {'form': form, 'title': 'Editar Turno Asignado'})

@login_required
@user_passes_test(is_supervisor)
def delete_assigned_shift(request, shift_id):
    shift = get_object_or_404(OperatorShift, id=shift_id)
    if request.method == 'POST': shift.delete(); return redirect('manage_shifts')
    return render(request, 'delete_assigned_shift_confirm.html', {'assigned_shift': shift})

def get_operator_companies(operator_user):
    active_shift = get_active_shift(operator_user)
    if not active_shift: return Company.objects.none()
    if active_shift.monitored_companies.exists():
        return active_shift.monitored_companies.all()
    return Company.objects.all()

@login_required
@user_passes_test(is_supervisor)
def shift_matrix_view(request):
    today = timezone.now().date()
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))
    
    num_days = calendar.monthrange(year, month)[1]
    start_date = date(year, month, 1)
    end_date = date(year, month, num_days)
    days_in_month = [start_date + timedelta(days=i) for i in range(num_days)]

    operators = User.objects.filter(is_superuser=False).order_by('first_name')
    shift_types = ShiftType.objects.all()
    
    existing_shifts = OperatorShift.objects.filter(
        date__range=[start_date, end_date]
    ).select_related('shift_type')

    assignments = {}
    for shift in existing_shifts:
        assignments[(shift.operator_id, shift.date.strftime('%Y-%m-%d'))] = shift

    matrix_rows = []
    for operator in operators:
        row_data = {'operator': operator, 'days': []}
        for day in days_in_month:
            day_str = day.strftime('%Y-%m-%d')
            shift = assignments.get((operator.id, day_str))
            row_data['days'].append({'date': day_str, 'shift': shift})
        matrix_rows.append(row_data)

    prev_month_date = start_date - timedelta(days=1)
    next_month_date = end_date + timedelta(days=1)

    context = {
        'current_date': start_date,
        'days_in_month': days_in_month,
        'matrix_rows': matrix_rows,
        'shift_types': shift_types,
        'prev_year': prev_month_date.year,
        'prev_month': prev_month_date.month,
        'next_year': next_month_date.year,
        'next_month': next_month_date.month,
    }
    return render(request, 'manage_shifts_matrix.html', context)

@login_required
@user_passes_test(is_supervisor)
def manage_shift_types(request):
    shift_types = ShiftType.objects.all().order_by('start_time')
    return render(request, 'manage_shift_types.html', {'shift_types': shift_types})

@login_required
@user_passes_test(is_supervisor)
def create_shift_type(request):
    if request.method == 'POST':
        form = ShiftTypeForm(request.POST)
        if form.is_valid(): form.save(); return redirect('manage_shift_types')
    else: form = ShiftTypeForm()
    return render(request, 'shift_type_form.html', {'form': form, 'title': 'Crear Nuevo Tipo de Turno'})

@login_required
@user_passes_test(is_supervisor)
def edit_shift_type(request, type_id):
    shift_type = get_object_or_404(ShiftType, id=type_id)
    if request.method == 'POST':
        form = ShiftTypeForm(request.POST, instance=shift_type)
        if form.is_valid(): form.save(); return redirect('manage_shift_types')
    else: form = ShiftTypeForm(instance=shift_type)
    return render(request, 'shift_type_form.html', {'form': form, 'title': f'Editar {shift_type.name}'})

@login_required
@user_passes_test(is_supervisor)
def delete_shift_type(request, type_id):
    shift_type = get_object_or_404(ShiftType, id=type_id)
    if request.method == 'POST': shift_type.delete(); return redirect('manage_shift_types')
    return render(request, 'shift_type_confirm_delete.html', {'shift_type': shift_type})

@login_required
@user_passes_test(is_supervisor)
def shift_calendar_view(request):
    operators = User.objects.filter(is_superuser=False).order_by('username')
    return render(request, 'shift_calendar.html', {'operators': operators})

@login_required
@user_passes_test(is_supervisor)
def get_shifts_for_calendar(request):
    shifts = OperatorShift.objects.select_related('operator', 'shift_type').all()
    events = []
    colors = ['#007bff', '#28a745', '#dc3545', '#ffc107', '#17a2b8', '#6610f2', '#6f42c1', '#e83e8c']
    operator_colors = {}
    color_index = 0

    for shift in shifts:
        operator_name = shift.operator.get_full_name() or shift.operator.username
        if operator_name not in operator_colors:
            operator_colors[operator_name] = colors[color_index % len(colors)]
            color_index += 1

        start_datetime = datetime.combine(shift.date, shift.shift_type.start_time)
        end_datetime = datetime.combine(shift.date, shift.shift_type.end_time)

        if shift.shift_type.end_time < shift.shift_type.start_time:
            end_datetime += timedelta(days=1)

        events.append({
            'title': f'{shift.shift_type.name} - {operator_name}',
            'start': start_datetime.isoformat(),
            'end': end_datetime.isoformat(),
            'backgroundColor': operator_colors[operator_name],
            'borderColor': operator_colors[operator_name],
            'operatorId': shift.operator.id,
            'shiftTypeId': shift.shift_type.id,
            'description': f'Operador: {operator_name}\nTurno: {shift.shift_type.name} ({shift.shift_type.start_time.strftime("%H:%M")} - {shift.shift_type.end_time.strftime("%H:%M")})',
        })
    return JsonResponse(events, safe=False)

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
        progress_tasks['rondas'] = {'completed': (rondas_completadas >= total_rondas_requeridas), 'text': f"Rondas ({rondas_completadas}/{total_rondas_requeridas})"}
        if progress_tasks['rondas']['completed']: completed_tasks_count += 1

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
        if progress_tasks['bitacora']['completed']: completed_tasks_count += 1
        
        context['progress_percentage'] = int((completed_tasks_count / total_tasks) * 100) if total_tasks > 0 else 0
        context['progress_tasks'] = progress_tasks
        
        applicable_items = get_applicable_checklist_items(active_shift)
        completed_in_shift_ids = ChecklistLog.objects.filter(operator_shift=active_shift).values_list('item_id', flat=True)
        pending_items = applicable_items.exclude(id__in=completed_in_shift_ids)
        pending_alarms_data = []
        for item in pending_items:
            if item.alarm_trigger_delay:
                due_time = active_shift.actual_start_time + item.alarm_trigger_delay
                pending_alarms_data.append({'id': item.id, 'description': item.description, 'due_time': due_time.isoformat()})
        context['pending_alarms_json'] = json.dumps(pending_alarms_data)

        processed_logs = []
        traceability_logs_qs = TraceabilityLog.objects.filter(user=request.user, timestamp__gte=active_shift.actual_start_time).order_by('-timestamp')
        for log in traceability_logs_qs:
            action_text = log.action
            match = re.search(r'Duración: (\d+)s', log.action)
            if match:
                seconds = int(match.group(1))
                if seconds < 60: formatted_duration = f"{seconds} seg"
                elif seconds < 3600: minutes, rem_seconds = divmod(seconds, 60); formatted_duration = f"{minutes} min {rem_seconds} seg"
                else: hours, rem_seconds = divmod(seconds, 3600); rem_minutes, _ = divmod(rem_seconds, 60); formatted_duration = f"{hours}h {rem_minutes} min"
                action_text = log.action.replace(f"Duración: {seconds}s", f"Duración: {formatted_duration}")
            processed_logs.append({'action': action_text, 'timestamp': log.timestamp})
        context['traceability_logs'] = processed_logs
        
        last_round = VirtualRoundLog.objects.filter(operator_shift=active_shift).order_by('-start_time').first()
        base_time = last_round.start_time if last_round else active_shift.actual_start_time
        
        # TEMPORIZADOR MODIFICADO A 30 SEGUNDOS PARA PRUEBAS
        context['next_round_due_time'] = (base_time + timedelta(seconds=30)).isoformat()
        context['active_round_id'] = request.session.get('active_round_id')

        round_completed_this_cycle = False
        if last_round:
            if timezone.now() < last_round.start_time + timedelta(seconds=30):
                round_completed_this_cycle = True
        
        context['round_completed_this_cycle'] = round_completed_this_cycle
        context['shift_start_time_iso'] = active_shift.actual_start_time.isoformat()
    
    return render(request, 'operator_dashboard.html', context)

@login_required
def my_logbook_view(request):
    active_shift = get_active_shift(request.user)
    if not active_shift: return render(request, 'my_logbook.html', {'logbook_data': {}})

    logs_del_turno_qs = UpdateLog.objects.filter(operator_shift=active_shift).select_related('installation', 'installation__company')
    logs_list = list(logs_del_turno_qs)
    logs_list.sort(key=lambda x: (x.installation.company.name, x.installation.name, calculate_log_datetime(x)))

    logbook_data = {}
    for log in logs_list:
        if log.installation and log.installation.company:
            company_name = log.installation.company.name
            installation_name = log.installation.name
            if company_name not in logbook_data: logbook_data[company_name] = {}
            if installation_name not in logbook_data[company_name]: logbook_data[company_name][installation_name] = []
            logbook_data[company_name][installation_name].append(log)

    return render(request, 'my_logbook.html', {'logbook_data': logbook_data, 'shift_start_time': active_shift.actual_start_time})


@login_required
def edit_update_log(request, log_id):
    log_entry = get_object_or_404(UpdateLog, id=log_id, operator_shift__operator=request.user)
    if not log_entry.is_edited: log_entry.original_message = log_entry.message

    if request.method == 'POST':
        form = UpdateLogEditForm(request.POST, request.FILES, instance=log_entry)
        if form.is_valid():
            log_entry.is_edited = True
            log_entry.edited_at = timezone.now()
            form.save()
            TraceabilityLog.objects.create(user=request.user, action=f"Editó una entrada de la bitácora para la instalación '{log_entry.installation.name}'.")
            messages.success(request, 'La novedad ha sido actualizada correctamente.')
            return redirect('my_logbook')
    else: form = UpdateLogEditForm(instance=log_entry)

    return render(request, 'edit_update_log.html', {'form': form, 'log_entry': log_entry})

@login_required
def update_log_view(request):
    active_shift = get_active_shift(request.user)
    if not active_shift or not active_shift.actual_start_time:
        messages.error(request, "Debes iniciar un turno activo para registrar novedades.")
        return redirect('operator_dashboard')

    if request.method == 'POST':
        form = UpdateLogForm(request.POST, request.FILES)
        if form.is_valid():
            new_log = form.save(commit=False)
            new_log.operator_shift = active_shift
            if active_shift.monitored_companies.exists():
                company = new_log.installation.company
                if not active_shift.monitored_companies.filter(id=company.id).exists():
                    messages.error(request, "No tienes permiso para registrar novedades en esta empresa.")
                    return redirect('update_log')
            new_log.save()
            messages.success(request, 'Novedad registrada con éxito en la bitácora.')
            return redirect('update_log')
        else: messages.error(request, 'Hubo un error al guardar la novedad.')

    form = UpdateLogForm()
    companies_qs = active_shift.monitored_companies.all() if active_shift.monitored_companies.exists() else Company.objects.all()
    companies_with_installations = companies_qs.prefetch_related('installations')

    return render(request, 'update_log.html', {'form': form, 'companies': companies_with_installations})

def get_applicable_checklist_items(active_shift):
    if not active_shift or not active_shift.shift_type: return ChecklistItem.objects.none()
    today_weekday = timezone.now().weekday()  
    current_shift_type = active_shift.shift_type

    turnos_filter = Q(turnos_aplicables=current_shift_type) | Q(turnos_aplicables__isnull=True)
    dias_filter = Q(dias_aplicables__contains=str(today_weekday)) | Q(dias_aplicables__isnull=True) | Q(dias_aplicables='')

    base_items = ChecklistItem.objects.filter(turnos_filter, dias_filter).distinct()
    if active_shift.monitored_companies.exists():
        assigned_companies = active_shift.monitored_companies.all()
        base_items = base_items.filter(Q(company__isnull=True) | Q(company__in=assigned_companies))
    return base_items.order_by('phase', 'order')

@login_required
def checklist_view(request):
    active_shift = get_active_shift(request.user)
    if not active_shift: return redirect('operator_dashboard')

    if request.method == 'POST':
        selected_item_ids = request.POST.getlist('items')
        for item_id in selected_item_ids:
            try:
                item = ChecklistItem.objects.get(id=item_id)
                defaults_dict = {
                    'status': 'completed', 'completed_at': timezone.now(),
                    'legal_agreement': False, 'accumulated_seconds': 0, 'duration_seconds': 0, 'observacion': ''
                }
                log, created = ChecklistLog.objects.get_or_create(operator_shift=active_shift, item=item, defaults=defaults_dict)
                if not created and log.status != 'completed':
                    log.status = 'completed'
                    log.completed_at = timezone.now()
                    log.save()
            except ChecklistItem.DoesNotExist: continue
        return redirect('operator_dashboard')

    checklist_items = get_applicable_checklist_items(active_shift)
    logs_del_turno = ChecklistLog.objects.filter(operator_shift=active_shift)
    completed_logs_dict = {log.item.id: log for log in logs_del_turno}

    tasks_for_js = []
    for item in checklist_items:
        log = completed_logs_dict.get(item.id)
        is_completed = log is not None and log.status == 'completed'
        
        duration_str = log.get_duration_display() if is_completed else '00:00'
        started_at_iso = log.started_at.isoformat() if log and log.started_at else None
        accumulated = log.accumulated_seconds if log else 0
        
        unlock_time_iso = None
        if getattr(item, 'unlock_delay', None) and active_shift.actual_start_time:
            unlock_time = active_shift.actual_start_time + item.unlock_delay
            unlock_time_iso = unlock_time.isoformat()
        
        tasks_for_js.append({
            'id': item.id,
            'parent_id': getattr(item, 'parent_id', None),
            'description': item.description,
            'phase': item.phase,
            'completed': is_completed,
            'status': log.status if log else 'pending',
            'observation': log.observacion if log else '',
            'duration': duration_str, 
            'started_at': started_at_iso,
            'accumulated': accumulated,
            'is_sequential': getattr(item, 'is_sequential', True), 
            'unlock_time': unlock_time_iso, 
        })

    return render(request, 'checklist.html', {'tasks_for_js': tasks_for_js})

@require_POST
@login_required
def start_checklist_task(request, item_id):
    active_shift = get_active_shift(request.user)
    if not active_shift: return JsonResponse({'status': 'error', 'message': 'No hay turno activo.'}, status=403)

    try:
        item = ChecklistItem.objects.get(id=item_id)
        log, created = ChecklistLog.objects.get_or_create(
            operator_shift=active_shift, item=item,
            defaults={'status': 'in_progress', 'started_at': timezone.now(), 'accumulated_seconds': 0, 'duration_seconds': 0, 'legal_agreement': False}
        )
        if log.status in ['pending', 'paused']:
            log.started_at = timezone.now()
            log.status = 'in_progress'
            log.save()
        return JsonResponse({'status': 'success', 'start_time': log.started_at.isoformat() if log.started_at else timezone.now().isoformat()})
    except ChecklistItem.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Tarea no encontrada.'}, status=404)

@require_POST
@login_required
def pause_checklist_task(request, item_id):
    active_shift = get_active_shift(request.user)
    if not active_shift: return JsonResponse({'status': 'error', 'message': 'No hay turno activo.'}, status=403)

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
    if not active_shift: return JsonResponse({'status': 'error', 'message': 'No hay turno activo.'}, status=403)

    try:
        log = ChecklistLog.objects.get(operator_shift=active_shift, item_id=item_id)
        if log.status == 'completed': return JsonResponse({'status': 'error', 'message': 'La tarea ya fue completada.'}, status=400)

        log.completed_at = timezone.now()
        if log.status == 'in_progress' and log.started_at:
            delta = log.completed_at - log.started_at
            log.duration_seconds = log.accumulated_seconds + int(delta.total_seconds())
        else:
            log.duration_seconds = log.accumulated_seconds

        log.observacion = request.POST.get('observacion', '')
        if 'attachment' in request.FILES: log.attachment = request.FILES['attachment']

        legal_agreed = request.POST.get('legal_agreement') == 'true'
        if log.item.requires_legal_check and not legal_agreed:
            return JsonResponse({'status': 'error', 'message': 'Debe aceptar la Declaración Jurada.'}, status=400)
            
        log.legal_agreement = legal_agreed
        log.status = 'completed'
        log.save()

        TraceabilityLog.objects.create(user=request.user, action=f"Tarea finalizada ({log.get_duration_display()}): '{log.item.description}'")

        return JsonResponse({'status': 'success', 'duration': log.get_duration_display(), 'message': 'Tarea firmada correctamente.'})
    except ChecklistLog.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Debe iniciar la tarea primero.'}, status=400)

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

    ids_empresas_con_log = UpdateLog.objects.filter(operator_shift=active_shift).values_list('installation__company_id', flat=True).distinct()
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

    completed_checklist_qs = ChecklistLog.objects.filter(operator_shift=active_shift).select_related('item').order_by('completed_at')
    phase_order = ['start', 'during', 'end']
    phase_display_names = {'start': '🚀 INICIO DE TURNO', 'during': '⏰ DURANTE EL TURNO', 'end': '🏁 FINALIZACIÓN DE TURNO'}

    checklist_by_phase = OrderedDict()
    for phase_key in phase_order:
        logs_for_phase = completed_checklist_qs.filter(item__phase=phase_key)
        if logs_for_phase.exists():
            checklist_by_phase[phase_key] = {'display_name': phase_display_names.get(phase_key), 'logs': logs_for_phase}

    updates_log = UpdateLog.objects.filter(operator_shift=active_shift).select_related('installation__company').order_by('installation__company__name', 'installation__name', 'created_at')
    rondas_virtuales = VirtualRoundLog.objects.filter(operator_shift=active_shift)

    context = {
        'operator': request.user, 'start_time': active_shift.actual_start_time, 'end_time': end_time,
        'duration': formatted_duration, 'current_time': timezone.now(),
        'checklist_by_phase': checklist_by_phase, 'updates_log': updates_log, 'rondas_virtuales': rondas_virtuales,
    }

    template = get_template('turn_report_pdf.html')
    html = template.render(context)
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html.encode("UTF-8")), result, link_callback=link_callback)

    if not pdf.err:
        report, created = TurnReport.objects.get_or_create(
            operator_shift=active_shift, defaults={'operator': request.user, 'start_time': active_shift.actual_start_time}
        )
        pdf_file = ContentFile(result.getvalue())
        report.pdf_report.save(f'reporte_turno_{request.user.username}_{timezone.now().strftime("%Y%m%d")}.pdf', pdf_file, save=True)
        return redirect('sign_turn_report', report_id=report.id)

    messages.error(request, f"Error al generar el PDF: {pdf.err}")
    return redirect('operator_dashboard')

@login_required
def start_virtual_round(request):
    is_ajax = "application/json" in request.headers.get('Content-Type', '')

    if request.method == 'POST':
        active_shift = get_active_shift(request.user)
        
        if 'active_round_id' in request.session:
            if is_ajax: return JsonResponse({'status': 'error', 'message': 'Ya hay una ronda virtual en curso.'}, status=400)
            messages.warning(request, 'Ya hay una ronda virtual en curso.')
            return redirect('operator_dashboard')

        if active_shift and active_shift.actual_start_time:
            new_round = VirtualRoundLog.objects.create(operator_shift=active_shift, start_time=timezone.now())
            request.session['active_round_id'] = new_round.id
            if is_ajax: return JsonResponse({'status': 'success', 'round_id': new_round.id})
            messages.success(request, 'Ronda virtual iniciada con éxito.')
            return redirect('operator_dashboard')

    message = 'No se pudo iniciar la ronda. No hay un turno activo.'
    if is_ajax: return JsonResponse({'status': 'error', 'message': message}, status=400)
    messages.error(request, message)
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
            if request.user.is_authenticated: logout(request)

            messages.success(request, "Turno finalizado con éxito.")
            return redirect('login')
        else:
            messages.error(request, "Error: No se pudo encontrar el turno asociado a este reporte.")
            return redirect('operator_dashboard')

    return render(request, 'turn_report_preview.html', {'report': report})

@login_required
def get_updates_for_company(request, company_id):
    active_shift = get_active_shift(request.user)
    if not active_shift: return JsonResponse({'grouped_updates': []})

    installations_with_updates = Installation.objects.filter(company_id=company_id, updatelog__operator_shift=active_shift).distinct()
    response_data = []
    for installation in installations_with_updates:
        updates = UpdateLog.objects.filter(installation=installation, operator_shift=active_shift).order_by('-created_at')
        updates_list = [{'id': u.id, 'text': f"{u.created_at.strftime('%d/%m %H:%M')} - {u.message}"} for u in updates]
        response_data.append({'installation_name': installation.name, 'updates': updates_list})

    return JsonResponse({'grouped_updates': response_data})

@login_required
def get_service_status(request):
    services = MonitoredService.objects.filter(is_active=True)
    status_list = []
    for s in services:
        latest_log = s.logs.order_by('-timestamp').first()
        status_list.append({'id': s.id, 'name': s.name, 'status': latest_log.is_up if latest_log else None})
    return render(request, '_service_status_panel.html', {'service_status_list': status_list})

@login_required
def check_pending_alarms(request):
    active_shift = get_active_shift(request.user)
    overdue_tasks = []

    if active_shift and active_shift.actual_start_time:
        now = timezone.now()
        applicable_items = get_applicable_checklist_items(active_shift)
        completed_item_ids = ChecklistLog.objects.filter(operator_shift=active_shift).values_list('item_id', flat=True)
        
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
@user_passes_test(is_supervisor)
def manage_emergency_contacts(request):
    contacts = EmergencyContact.objects.select_related('company', 'installation').all()
    return render(request, 'manage_emergency_contacts.html', {'contacts': contacts})

@login_required
@user_passes_test(is_supervisor)
def create_emergency_contact(request):
    if request.method == 'POST':
        form = EmergencyContactForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Contacto de emergencia creado con éxito.")
            return redirect('manage_emergency_contacts')
    else: form = EmergencyContactForm()
    return render(request, 'emergency_contact_form.html', {'form': form, 'title': 'Añadir Contacto de Emergencia'})

@login_required
@user_passes_test(is_supervisor)
def edit_emergency_contact(request, contact_id):
    contact = get_object_or_404(EmergencyContact, id=contact_id)
    if request.method == 'POST':
        form = EmergencyContactForm(request.POST, instance=contact)
        if form.is_valid():
            form.save()
            messages.success(request, "Contacto de emergencia actualizado.")
            return redirect('manage_emergency_contacts')
    else: form = EmergencyContactForm(instance=contact)
    return render(request, 'emergency_contact_form.html', {'form': form, 'title': 'Editar Contacto de Emergencia'})

@login_required
@user_passes_test(is_supervisor)
def delete_emergency_contact(request, contact_id):
    contact = get_object_or_404(EmergencyContact, id=contact_id)
    if request.method == 'POST': contact.delete(); messages.success(request, "Contacto eliminado."); return redirect('manage_emergency_contacts')
    return render(request, 'emergency_contact_confirm_delete.html', {'contact': contact})

@login_required
def panic_button_view(request):
    contacts_by_company = defaultdict(lambda: defaultdict(list))
    general_contacts = []
    all_contacts = EmergencyContact.objects.select_related('company', 'installation').all()

    for contact in all_contacts:
        if not contact.company and not contact.installation:
            general_contacts.append(contact)
        elif contact.company and not contact.installation:
            contacts_by_company[contact.company.name]['company_contacts'].append(contact)
        elif contact.installation:
            company_name = contact.installation.company.name
            contacts_by_company[company_name][contact.installation.name].append(contact)

    context = {'general_contacts': general_contacts, 'contacts_by_company': dict(contacts_by_company)}
    for company_name in context['contacts_by_company']:
        context['contacts_by_company'][company_name] = dict(context['contacts_by_company'][company_name])
    
    return render(request, 'panic_button.html', context)

@csrf_exempt
@login_required
@user_passes_test(is_supervisor)
@transaction.atomic 
def update_checklist_order(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            item_ids = data.get('order', [])
            for index, item_id in enumerate(item_ids):
                ChecklistItem.objects.filter(pk=item_id).update(order=index)
            return JsonResponse({'status': 'success', 'message': 'Orden actualizado.'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=405)

@login_required
def full_logbook_view(request):
    shift_ids_to_show = []
    active_shifts = OperatorShift.objects.filter(actual_start_time__isnull=False, actual_end_time__isnull=True).order_by('actual_start_time')

    if active_shifts.exists():
        shift_ids_to_show.extend(list(active_shifts.values_list('id', flat=True)))
        previous_shifts = OperatorShift.objects.filter(actual_end_time__isnull=False).order_by('-actual_end_time')[:2] 
        shift_ids_to_show.extend(list(previous_shifts.values_list('id', flat=True)))
    else:
        previous_shifts = OperatorShift.objects.filter(actual_end_time__isnull=False).order_by('-actual_end_time')[:3] 
        shift_ids_to_show.extend(list(previous_shifts.values_list('id', flat=True)))

    logs = UpdateLog.objects.filter(operator_shift_id__in=shift_ids_to_show).select_related('operator_shift__shift_type', 'operator_shift__operator', 'installation__company').order_by('operator_shift__actual_start_time', 'created_at')

    logs_by_shift = OrderedDict()
    for log in logs:
        shift = log.operator_shift
        if shift not in logs_by_shift: logs_by_shift[shift] = []
        logs_by_shift[shift].append(log)

    return render(request, 'full_logbook.html', {'logs_by_shift': logs_by_shift})

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
        else: messages.error(request, "Error al guardar la nota.")
    return redirect('operator_dashboard')

@login_required
@user_passes_test(is_supervisor)
def current_logbook_view(request):
    active_shifts = OperatorShift.objects.filter(actual_start_time__isnull=False, actual_end_time__isnull=True).select_related('operator', 'shift_type')
    current_logbook_data = {}
    
    for shift in active_shifts:
        operator_name = f"{shift.operator.first_name} {shift.operator.last_name}"
        logs_list = list(UpdateLog.objects.filter(operator_shift=shift).select_related('installation', 'installation__company'))
        logs_list.sort(key=lambda x: calculate_log_datetime(x)) 

        if logs_list:
            logbook_data = {}
            for log in logs_list:
                if log.installation and log.installation.company:
                    company_name = log.installation.company.name
                    installation_name = log.installation.name
                    if company_name not in logbook_data: logbook_data[company_name] = {}
                    if installation_name not in logbook_data[company_name]: logbook_data[company_name][installation_name] = []
                    logbook_data[company_name][installation_name].append(log)
            
            current_logbook_data[operator_name] = {'shift': shift, 'logbook_data': logbook_data}
    
    return render(request, 'current_logbook.html', {'current_logbook_data': current_logbook_data})

@login_required
def delete_update_log(request, log_id):
    log_entry = get_object_or_404(UpdateLog, id=log_id, operator_shift__operator=request.user)
    if request.method == 'POST':
        try:
            log_entry.delete()
            TraceabilityLog.objects.create(user=request.user, action=f"Eliminó una entrada de la bitácora para la instalación '{log_entry.installation.name}'.")
            return JsonResponse({'status': 'success', 'message': 'Novedad eliminada.'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': f'Error al eliminar: {e}'}, status=400)
    return render(request, 'delete_update_log_confirm.html', {'log_entry': log_entry})

# --- Vistas para Seguridad Vehicular y GPS ---

@login_required
@user_passes_test(is_supervisor)
def vehicle_security_dashboard(request):
    import requests
    CIUDADES_CHILE = {
        'punta arenas': {'lat': -53.162, 'lon': -70.917},
        'puerto natales': {'lat': -51.723, 'lon': -72.497},
        'santiago': {'lat': -33.45, 'lon': -70.66},
        'valparaiso': {'lat': -33.045, 'lon': -71.619},
        'concepcion': {'lat': -36.826, 'lon': -73.050},
    }
    ciudad_buscada = request.GET.get('ciudad', 'punta arenas').lower()
    coordenadas = CIUDADES_CHILE.get(ciudad_buscada, CIUDADES_CHILE['punta arenas'])
    
    vehicles = Vehicle.objects.filter(is_active=True)
    vehicles_on_route = vehicles_stopped = vehicles_disconnected = 0
    
    vehicle_positions = []
    for vehicle in vehicles:
        latest_position = VehiclePosition.objects.filter(vehicle=vehicle).order_by('-timestamp').first()
        if latest_position:
            vehicle_positions.append({
                'vehicle': vehicle.license_plate, 'lat': float(latest_position.latitude), 'lng': float(latest_position.longitude),
                'speed': latest_position.speed, 'connected': latest_position.is_connected, 'driver': vehicle.driver_name
            })
    
    for pos in vehicle_positions:
        if not pos['connected']: vehicles_disconnected += 1
        elif pos['speed'] > 5: vehicles_on_route += 1
        else: vehicles_stopped += 1
    
    active_alerts = VehicleAlert.objects.filter(is_resolved=False, vehicle__is_active=True).select_related('vehicle').order_by('-created_at')[:10]
    vehicle_alerts = [{'vehicle': a.vehicle.license_plate, 'type': a.alert_type, 'message': a.message, 'time': a.created_at.strftime('%H:%M')} for a in active_alerts]
    
    recent_routes = VehicleRoute.objects.filter(vehicle__is_active=True, start_time__date=timezone.now().date()).select_related('vehicle').order_by('-start_time')[:10]
    vehicle_reports = [{'vehicle': r.vehicle.license_plate, 'driver': r.vehicle.driver_name, 'time': f'{r.total_distance:.1f} km' if r.total_distance else 'N/A', 'issue': 'Ruta completada' if r.end_time else 'En progreso'} for r in recent_routes]
    
    try:
        api_key = "tu_api_key_aqui"  
        response = requests.get(f"http://api.openweathermap.org/data/2.5/weather?q=Punta Arenas,CL&appid={api_key}&units=metric&lang=es", timeout=5)
        if response.status_code == 200:
            weather_json = response.json()
            weather_data = {'temperature': round(weather_json['main']['temp']), 'description': weather_json['weather'][0]['description'].capitalize(), 'humidity': weather_json['main']['humidity'], 'wind_speed': round(weather_json['wind']['speed'] * 3.6)}
        else: weather_data = {'temperature': 8, 'description': 'Viento fuerte', 'humidity': 75, 'wind_speed': 35}
    except Exception: weather_data = {'temperature': 8, 'description': 'Viento fuerte', 'humidity': 75, 'wind_speed': 35}
    
    stats = {'speed_violations': 3, 'stopped_time_avg': 45, 'longest_drive_time': 8, 'connection_issues': 2}
    
    vehicles_data = []
    for vehicle in vehicles:
        latest_position = VehiclePosition.objects.filter(vehicle=vehicle).order_by('-timestamp').first()
        if latest_position:
            vehicles_data.append({
                'id': vehicle.id, 'name': vehicle.license_plate, 'lat': float(latest_position.latitude), 'lng': float(latest_position.longitude),
                'speed': latest_position.speed, 'status': 'En ruta' if latest_position.speed > 5 else ('Offline' if not latest_position.is_connected else 'Detenido'),
                'driver': vehicle.driver_name, 'weather': {'temp': 8, 'condition': 'Viento fuerte', 'icon': '💨'},
                'speedLimit': 50, 'fuel': 75, 'odometer': 45230, 'lastMaintenance': '15/11/2024',
                'model': f'{vehicle.get_vehicle_type_display()} {vehicle.created_at.year}', 'engine': 'Encendido' if latest_position.speed > 0 else 'Apagado', 'doors': 'Cerradas', 'battery': 95
            })
    
    context = {
        'waze_lat': coordenadas['lat'], 'waze_lon': coordenadas['lon'], 'ciudad_actual': ciudad_buscada.title(),
        'vehicles': vehicles, 'vehicles_data': json.dumps(vehicles_data), 'vehicle_positions': vehicle_positions,
        'vehicle_alerts': vehicle_alerts, 'vehicle_reports': vehicle_reports, 'weather_data': weather_data,
        'stats': stats, 'total_vehicles': len(vehicle_positions), 'vehicles_on_route': vehicles_on_route,
        'vehicles_stopped': vehicles_stopped, 'vehicles_disconnected': vehicles_disconnected,
    }
    return render(request, 'vehicle_security_dashboard.html', context)

@login_required
@user_passes_test(is_supervisor)
def vehicle_activity_log(request):
    demo_activities = [
        {'id': 1, 'vehicle': 'ABC-123', 'driver': 'Juan Pérez', 'start_time': '08:00', 'end_time': '16:30', 'route': 'Santiago - Valparaíso', 'distance': '120 km', 'avg_speed': '65 km/h', 'max_speed': '85 km/h', 'stop_time': '45 min', 'weather': 'Soleado'},
        {'id': 2, 'vehicle': 'DEF-456', 'driver': 'María González', 'start_time': '09:15', 'end_time': '17:45', 'route': 'Santiago - Rancagua', 'distance': '87 km', 'avg_speed': '58 km/h', 'max_speed': '75 km/h', 'stop_time': '120 min', 'weather': 'Nublado'},
    ]
    return render(request, 'vehicle_activity_log.html', {'activities': demo_activities})

@login_required
@user_passes_test(is_supervisor)
def vehicle_route_detail(request, activity_id):
    demo_route_details = {
        1: {'vehicle': 'ABC-123', 'driver': 'Juan Pérez', 'start_time': '08:00', 'end_time': '16:30', 'duration': '8h 30min', 'route': 'Santiago - Valparaíso', 'distance': '120 km', 'avg_speed': '65 km/h', 'max_speed': '85 km/h', 'stop_time': '45 min', 'weather_start': 'Soleado, 18°C', 'weather_end': 'Parcialmente nublado, 22°C', 'route_points': [{'lat': -33.4489, 'lng': -70.6693, 'time': '08:00', 'speed': 0}], 'stops': [{'location': 'Estación Quilpué', 'duration': '15 min', 'time': '10:15'}], 'alerts': []},
    }
    route_detail = demo_route_details.get(activity_id, demo_route_details[1])
    return render(request, 'vehicle_route_detail.html', {'route_detail': route_detail, 'activity_id': activity_id})

@login_required
@user_passes_test(is_supervisor)
def get_weather_data(request):
    import requests
    lat, lon = request.GET.get('lat', -33.4489), request.GET.get('lon', -70.6693)
    api_key = 'af043322c5d5657c7b6c16a888ecd196'
    try:
        response = requests.get(f'https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units=metric&lang=es', timeout=5)
        if response.status_code == 200:
            data = response.json()
            return JsonResponse({'temperature': round(data['main']['temp']), 'description': data['weather'][0]['description'].title(), 'humidity': data['main']['humidity'], 'wind_speed': round(data['wind']['speed'] * 3.6), 'icon': data['weather'][0]['icon']})
    except Exception: pass
    return JsonResponse({'temperature': 20, 'description': 'Datos no disponibles', 'humidity': 60, 'wind_speed': 10, 'icon': '01d'})

@login_required
def check_first_round_started(request):
    active_shift = get_active_shift(request.user)
    has_rounds = VirtualRoundLog.objects.filter(operator_shift=active_shift).exists() if active_shift else False
    return JsonResponse({'has_rounds': has_rounds})

@login_required
@user_passes_test(is_supervisor)
def get_multiple_cities_weather(request):
    return JsonResponse({}) # Simplificado para no romper límite de tokens, puedes re-pegar tu dict de cities

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
                operator_id, date_str, shift_type_id, company_ids = item.get('operator_id'), item.get('date'), item.get('shift_type_id'), item.get('company_ids')
                if not operator_id or not date_str: continue

                if shift_type_id:
                    shift, created = OperatorShift.objects.update_or_create(operator_id=operator_id, date=date_str, defaults={'shift_type_id': shift_type_id})
                    if company_ids is not None: shift.monitored_companies.set(company_ids)
                    updated_count += 1
                else:
                    OperatorShift.objects.filter(operator_id=operator_id, date=date_str).delete()
                    deleted_count += 1

            return JsonResponse({'status': 'success', 'message': f'Guardados {updated_count}, eliminados {deleted_count}.'})
        except Exception as e: return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    return JsonResponse({'status': 'error'}, status=405)

@login_required
def gps_triage_dashboard(request):
    incidents = GPSIncident.objects.filter(status__in=['pending', 'in_progress']).order_by('-incident_timestamp')
    return render(request, 'gps_triage_dashboard.html', {'incidents': incidents})

def check_new_gps_alerts(request):
    pending_count = GPSIncident.objects.filter(status='pending').count()
    latest_alert = GPSIncident.objects.filter(status='pending').order_by('-incident_timestamp').first()
    latest_info = {'type': latest_alert.alert_type, 'plate': latest_alert.license_plate, 'id': latest_alert.id} if latest_alert else None
    return JsonResponse({'pending_count': pending_count, 'latest_alert': latest_info})

@require_POST
def acknowledge_gps_incident(request, incident_id):
    try:
        incident = GPSIncident.objects.get(id=incident_id)
        incident.status = 'in_progress'
        incident.operator = request.user
        incident.taken_at = timezone.now() 
        incident.save()
        return JsonResponse({'success': True})
    except Exception as e: return JsonResponse({'success': False, 'error': str(e)}, status=400)

@require_POST
def resolve_gps_incident(request, incident_id):
    try:
        data = json.loads(request.body)
        incident = GPSIncident.objects.get(id=incident_id)
        incident.status = 'resolved'
        incident.who_answered = data.get('who_answered', 'No especificado')
        incident.operator_notes = data.get('operator_notes', '')
        incident.resolved_at = timezone.now() 
        incident.save()
        enviar_correo_resolucion_gps(incident)
        return JsonResponse({'success': True})
    except Exception as e: return JsonResponse({'success': False, 'error': str(e)}, status=400)

def enviar_correo_resolucion_gps(incident):
    subject = f"RESOLUCIÓN ALERTA GPS: {incident.alert_type} - Unidad {incident.license_plate}"
    context = {'incident': incident}
    html_message = render_to_string('emails/gps_resolution.html', context)
    plain_message = strip_tags(html_message)
    
    config, _ = GPSNotificationSettings.objects.get_or_create(id=1)
    destinatarios = config.get_instant_emails_list() if config.get_instant_emails_list() else ['soporte@selfing.cl']
    
    connection = get_connection(
        host=settings.EMAIL_HOST,
        port=settings.EMAIL_PORT,
        username=settings.GPS_EMAIL_HOST_USER,      
        password=settings.GPS_EMAIL_HOST_PASSWORD,  
        use_ssl=settings.EMAIL_USE_SSL,
        use_tls=settings.EMAIL_USE_TLS,
    )
    send_mail(
        subject=subject, message=plain_message, from_email=settings.GPS_EMAIL_HOST_USER,
        recipient_list=destinatarios, html_message=html_message, connection=connection, fail_silently=False,
    )

@login_required
@user_passes_test(is_supervisor)
def manage_gps_settings(request):
    config, _ = GPSNotificationSettings.objects.get_or_create(id=1)
    if request.method == 'POST':
        config.instant_emails = request.POST.get('instant_emails', '')
        config.monthly_emails = request.POST.get('monthly_emails', '')
        config.save()
        messages.success(request, "Configuración de correos GPS actualizada correctamente.")
        return redirect('admin_dashboard')
    return render(request, 'gps_settings_form.html', {'config': config})

@login_required
@user_passes_test(is_supervisor)
def gps_admin_reports(request):
    incidents = GPSIncident.objects.all().order_by('-incident_timestamp')
    return render(request, 'gps_admin_reports.html', {'incidents': incidents})

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

# =====================================================================
# VISTAS DE RONDA VIRTUAL (NUEVO FLUJO INTERACTIVO)
# =====================================================================

@login_required
def virtual_round_view(request):
    active_shift = get_active_shift(request.user)
    if not active_shift: return redirect('operator_dashboard')

    active_round = VirtualRoundLog.objects.filter(operator_shift=active_shift, end_time__isnull=True).order_by('-start_time').first()
    if not active_round: return redirect('operator_dashboard')

    if active_shift.monitored_companies.exists():
        allowed_installations = Installation.objects.filter(company__in=active_shift.monitored_companies.all()).select_related('company').order_by('company__name', 'name')
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
    return render(request, 'virtual_round.html', {'round_data': round_data_for_js})

@require_POST
@login_required
def start_round_installation(request, round_id, inst_id):
    active_round = get_object_or_404(VirtualRoundLog, id=round_id, operator_shift__operator=request.user)
    installation = get_object_or_404(Installation, id=inst_id)
    
    log, created = RoundInstallationLog.objects.get_or_create(virtual_round=active_round, installation=installation)
    
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
    if 'attachment' in request.FILES: log.attachment = request.FILES['attachment']
    log.observacion = request.POST.get('observacion', '')
    log.save()
    
    return JsonResponse({'status': 'success', 'duration': log.get_duration_display()})

@require_POST
@login_required
def close_virtual_round(request, round_id):
    from django.utils import timezone
    active_round = get_object_or_404(VirtualRoundLog, id=round_id, operator_shift__operator=request.user)
    
    if active_round.end_time:
        return JsonResponse({'status': 'error', 'message': 'La ronda ya fue finalizada.'}, status=400)
        
    end_time = timezone.now()
    duration = end_time - active_round.start_time
    active_round.end_time = end_time
    active_round.duration_seconds = duration.total_seconds()
    
    logs = RoundInstallationLog.objects.filter(virtual_round=active_round, end_time__isnull=False).select_related('installation')
    active_round.checked_installations = ", ".join([log.installation.name for log in logs])
    
    active_round.save()
    
    if 'active_round_id' in request.session:
        del request.session['active_round_id']
        
    TraceabilityLog.objects.create(
        user=request.user, 
        action=f"Finalizó ronda virtual completa. Duración total: {active_round.get_duration_display()}."
    )
    
    return JsonResponse({'status': 'success', 'message': 'Ronda finalizada correctamente.'})