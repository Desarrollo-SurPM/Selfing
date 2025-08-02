# desarrollo-surpm/selfing/Selfing-mejorasorden/core/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.template.loader import get_template
from xhtml2pdf import pisa
from collections import defaultdict
from django.contrib import messages
from io import BytesIO
from django.db import transaction
from django.core.files.base import ContentFile
from django import forms
from datetime import timedelta, datetime
from django.contrib.auth import logout
from collections import OrderedDict
import json
from django.views.decorators.csrf import csrf_exempt 
import re # Importar el módulo de expresiones regulares

from .models import (
    Company, Installation, OperatorProfile, ShiftType, OperatorShift,
    ChecklistItem, ChecklistLog, VirtualRoundLog, UpdateLog, Email,
    TurnReport, MonitoredService, ServiceStatusLog, TraceabilityLog
)
from .forms import (
    UpdateLogForm, EmailForm, EmailApprovalForm, OperatorCreationForm,
    OperatorChangeForm, CompanyForm, InstallationForm, ChecklistItemForm,
    MonitoredServiceForm, ShiftTypeForm, OperatorShiftForm, VirtualRoundCompletionForm
)

def is_supervisor(user):
    return user.is_superuser

# core/views.py

@login_required
def home(request):
    """ Redirige al usuario a su dashboard correspondiente sin iniciar el turno. """
    if is_supervisor(request.user):
        return redirect('admin_dashboard')
    else:
        return redirect('operator_dashboard')

# --- VISTAS DE ADMINISTRADOR ---

@login_required
@user_passes_test(is_supervisor)
def admin_dashboard(request):
    today = timezone.now().date()
    
    # --- CAMBIO AQUÍ ---
    # Contamos los turnos de hoy que han iniciado pero no han terminado.
    operadores_en_turno = OperatorShift.objects.filter(
        date=today,
        actual_start_time__isnull=False,
        actual_end_time__isnull=True
    ).count()
    # --- FIN DEL CAMBIO ---

    novedades_hoy = UpdateLog.objects.filter(created_at__date=today).count()
    correos_pendientes_count = Email.objects.filter(status='pending').count()
    servicios_monitoreados_activos = MonitoredService.objects.filter(is_active=True).count()
    traceability_logs = TraceabilityLog.objects.select_related('user').all().order_by('-timestamp')[:6]
    reports = UpdateLog.objects.filter(created_at__date=today).select_related(
        'operator_shift__operator', 'installation__company'
    ).order_by('-created_at')
    pending_emails = Email.objects.filter(status='pending').select_related('company', 'operator').order_by('-created_at')

    context = {
        'novedades_hoy': novedades_hoy,
        'correos_pendientes_count': correos_pendientes_count,
        # Pasamos la nueva variable al contexto
        'operadores_en_turno': operadores_en_turno,
        'servicios_monitoreados_activos': servicios_monitoreados_activos,
        'reports': reports,
        'pending_emails': pending_emails,
        'traceability_logs': traceability_logs,
    }
    return render(request, 'admin_dashboard.html', context)

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
    
    # --- 👇 LÍNEA NUEVA AÑADIDA 👇 ---
    # Contamos todos los objetos de Instalación que existen en la base de datos
    total_installations = Installation.objects.count()
    # --- 👆 FIN DE LA LÍNEA NUEVA 👆 ---

    context = {
        'companies': companies,
        'total_installations': total_installations, # <-- Pasamos el nuevo dato a la plantilla
    }
    
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
    # --- 👇 CAMBIO AQUÍ: Nos aseguramos de que los items se obtengan en el orden correcto 👇 ---
    items = ChecklistItem.objects.all() # El orden por defecto ya está en el modelo
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
def review_and_approve_email(request, email_id):
    email = get_object_or_404(Email, id=email_id)
    if request.method == 'POST':
        form = EmailApprovalForm(request.POST, instance=email)
        if form.is_valid():
            form.save(); email.status = 'approved'; email.approved_by = request.user; email.approved_at = timezone.now()
            email.save(update_fields=['status', 'approved_by', 'approved_at'])
            TraceabilityLog.objects.create(user=request.user, action=f"Revisó y aprobó correo para {email.company.name}")
            return redirect('admin_dashboard')
    else: form = EmailApprovalForm(instance=email)
    return render(request, 'review_email.html', {'email': email, 'form': form, 'updates_list': email.updates.all()})

@login_required
@user_passes_test(is_supervisor)
def view_turn_reports(request):
    reports = TurnReport.objects.filter(is_signed=True)

    # Filtering
    operator_id = request.GET.get('operator')
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    order_by = request.GET.get('order_by', '-end_time') # Default sorting

    if operator_id:
        reports = reports.filter(operator_id=operator_id)
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            reports = reports.filter(end_time__date__gte=start_date)
        except ValueError:
            pass # Handle invalid date format
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            reports = reports.filter(end_time__date__lte=end_date)
        except ValueError:
            pass # Handle invalid date format

    # Ordering
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


# --- VISTAS PARA GESTIONAR TURNOS ---

@login_required
@user_passes_test(is_supervisor)
def manage_shifts(request):
    start_date = timezone.now().date()
    end_date = start_date + timedelta(days=7)
    assigned_shifts = OperatorShift.objects.filter(date__range=[start_date, end_date]).order_by('date', 'shift_type__start_time')
    return render(request, 'manage_shifts.html', {'assigned_shifts': assigned_shifts})

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

# --- VISTAS PARA GESTIONAR LOS TIPOS DE TURNO ---

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

# --- Rutas del calendario ---

@login_required
@user_passes_test(is_supervisor)
def shift_calendar_view(request):
    operators = User.objects.filter(is_superuser=False).order_by('username')
    context = {'operators': operators}
    return render(request, 'shift_calendar.html', context)


@login_required
@user_passes_test(is_supervisor)
def get_shifts_for_calendar(request):
    shifts = OperatorShift.objects.select_related('operator', 'shift_type').all()
    events = []
    
    # Simple color palette for operators
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

        # Handle overnight shifts: if end_time is earlier than start_time, it means it goes into the next day
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
    """Función robusta para obtener el turno activo más reciente de un operador."""
    shift = OperatorShift.objects.filter(
        operator=user,
        actual_end_time__isnull=True
    ).order_by('-date').first()
    return shift
    """
    Función robusta para obtener el turno activo más reciente de un operador.
    Busca el último turno asignado que aún no ha sido finalizado.
    """
    # Esta consulta ordena por fecha descendente, asegurando que siempre
    # obtengamos el turno más nuevo, solucionando el problema de la medianoche.
    shift = OperatorShift.objects.filter(
        operator=user,
        actual_end_time__isnull=True
    ).order_by('-date').first()
    
    return shift
# --- VISTAS DE OPERADOR ---

@login_required
def my_logbook_view(request):
    """
    Muestra al operador un resumen de sus novedades.
    VERSIÓN SIMPLIFICADA Y ROBUSTA.
    """
    active_shift = get_active_shift(request.user)
    
    # Si no hay turno activo, devolvemos un diccionario vacío.
    if not active_shift:
        return render(request, 'my_logbook.html', {'logbook_data': {}})

    # 1. Hacemos la consulta más directa posible.
    logs_del_turno = UpdateLog.objects.filter(
        operator_shift=active_shift
    ).select_related('installation', 'installation__company').order_by('created_at')

    # Si la consulta no devuelve nada, devolvemos un diccionario vacío.
    if not logs_del_turno.exists():
        return render(request, 'my_logbook.html', {'logbook_data': {}})

    # 2. Agrupamos los datos manualmente para asegurar la estructura correcta.
    logbook_data = {}
    for log in logs_del_turno:
        # Verificamos que el log tenga la información necesaria
        if log.installation and log.installation.company:
            company_name = log.installation.company.name
            installation_name = log.installation.name
            
            # Si la empresa no existe en nuestro diccionario, la creamos.
            if company_name not in logbook_data:
                logbook_data[company_name] = {}
            
            # Si la instalación no existe dentro de la empresa, la creamos.
            if installation_name not in logbook_data[company_name]:
                logbook_data[company_name][installation_name] = []
            
            # Finalmente, añadimos la novedad a la lista correcta.
            logbook_data[company_name][installation_name].append(log)

    context = {
        'logbook_data': logbook_data,
        'shift_start_time': active_shift.actual_start_time
    }
    
    return render(request, 'my_logbook.html', context)
    """
    Muestra al operador un resumen de sus novedades.
    VERSIÓN FINAL: Esta vista busca las novedades del turno activo, pero si no
    encuentra, busca todas las novedades del usuario en las últimas 24 horas
    para asegurar que siempre vea su trabajo reciente.
    """
    active_shift = get_active_shift(request.user)
    log_entries = None

    # Estrategia 1: Intentar obtener los logs del turno activo actual (el método más preciso)
    if active_shift and active_shift.actual_start_time:
        log_entries = UpdateLog.objects.filter(
            operator_shift=active_shift
        ).select_related('installation__company').order_by('created_at')

    # Estrategia 2 (Plan B): Si no se encontraron logs con el turno activo,
    # buscamos todos los logs creados por el usuario en las últimas 24 horas.
    if not log_entries:
        time_threshold = timezone.now() - timedelta(hours=24)
        log_entries = UpdateLog.objects.filter(
            operator_shift__operator=request.user,
            created_at__gte=time_threshold
        ).select_related('installation__company').order_by('created_at')
    
    # Si después de ambas estrategias no hay logs, mostramos la página vacía.
    if not log_entries:
        messages.info(request, "No has registrado novedades en tu turno actual.")
        return render(request, 'my_logbook.html', {'logbook_data': None})

    # Si encontramos logs (con cualquiera de las dos estrategias), los procesamos.
    logbook_data = defaultdict(lambda: defaultdict(list))
    for log in log_entries:
        if log.installation and log.installation.company:
            company_name = log.installation.company.name
            installation_name = log.installation.name
            logbook_data[company_name][installation_name].append(log)

    context = {
        'logbook_data': dict(logbook_data),
        'shift_start_time': active_shift.actual_start_time if active_shift else None
    }
    
    return render(request, 'my_logbook.html', context)


@login_required
def operator_dashboard(request):
    active_shift = get_active_shift(request.user)
    
    progress_tasks = {}
    completed_tasks_count = 0
    total_tasks = 3 
    next_round_due_time = None

    if active_shift and active_shift.actual_start_time:
        # --- Lógica de Progreso (sin cambios) ---
        total_rondas_requeridas = 7
        rondas_completadas = VirtualRoundLog.objects.filter(operator_shift=active_shift).count()
        rondas_completas = rondas_completadas >= total_rondas_requeridas
        progress_tasks['rondas'] = {'completed': rondas_completas, 'text': f"Realizar Rondas Virtuales ({rondas_completadas}/{total_rondas_requeridas})"}
        if rondas_completas: completed_tasks_count += 1

        empresas_con_instalaciones = Company.objects.filter(installations__isnull=False).distinct()
        ids_empresas_con_log = UpdateLog.objects.filter(operator_shift=active_shift).values_list('installation__company_id', flat=True).distinct()
        bitacora_completa = len(ids_empresas_con_log) >= empresas_con_instalaciones.count()
        progress_tasks['bitacora'] = {'completed': bitacora_completa, 'text': f"Anotar en Bitácora ({len(ids_empresas_con_log)}/{empresas_con_instalaciones.count()} empresas)"}
        if bitacora_completa: completed_tasks_count += 1
        
        todas_las_empresas = Company.objects.all()
        ids_empresas_con_correo = Email.objects.filter(operator=request.user, created_at__gte=active_shift.actual_start_time).values_list('company_id', flat=True)
        correos_completos = len(ids_empresas_con_correo) >= todas_las_empresas.count()
        progress_tasks['correos'] = {'completed': correos_completos, 'text': f"Enviar Correos de Novedades ({len(ids_empresas_con_correo)}/{todas_las_empresas.count()} empresas)"}
        if correos_completos: completed_tasks_count += 1
            
    progress_percentage = int((completed_tasks_count / total_tasks) * 100) if total_tasks > 0 else 0
    
    pending_checklist_items = []
    processed_logs = []

    if active_shift and active_shift.actual_start_time:
        completed_in_shift_ids = ChecklistLog.objects.filter(operator_shift=active_shift).values_list('item_id', flat=True)
        pending_items = ChecklistItem.objects.exclude(id__in=completed_in_shift_ids)
        for item in pending_items:
            pending_checklist_items.append({'description': item.description, 'offset_minutes': item.trigger_offset_minutes})

        # --- 👇 CAMBIO AQUÍ: Obtenemos TODOS los logs del turno para el scroll 👇 ---
        traceability_logs_qs = TraceabilityLog.objects.filter(
            user=request.user,
            timestamp__gte=active_shift.actual_start_time
        ).order_by('-timestamp') # No limitamos aquí para que el scroll funcione

        for log in traceability_logs_qs:
            action_text = log.action
            match = re.search(r'Duración: (\d+)s', log.action)
            if match:
                seconds = int(match.group(1))
                if seconds < 60: formatted_duration = f"{seconds} seg"
                elif seconds < 3600:
                    minutes = seconds // 60; rem_seconds = seconds % 60
                    formatted_duration = f"{minutes} min {rem_seconds} seg"
                else:
                    hours = seconds // 3600; rem_minutes = (seconds % 3600) // 60
                    formatted_duration = f"{hours}h {rem_minutes} min"
                action_text = log.action.replace(f"Duración: {seconds}s", f"Duración: {formatted_duration}")
            processed_logs.append({'action': action_text, 'timestamp': log.timestamp})
        
        # --- Lógica del Temporizador (verificada) ---
        ROUND_INTERVAL_MINUTES = 60
        last_round = VirtualRoundLog.objects.filter(operator_shift=active_shift).order_by('-start_time').first()
        
        base_time = last_round.start_time if last_round else active_shift.actual_start_time
        next_round_due_time = (base_time + timedelta(minutes=ROUND_INTERVAL_MINUTES)).isoformat()
        
    context = {
        'active_shift': active_shift,
        'progress_tasks': progress_tasks,
        'progress_percentage': progress_percentage,
        'active_round_id': request.session.get('active_round_id'),
        'pending_checklist_json': json.dumps(pending_checklist_items),
        'traceability_logs': processed_logs, # Pasamos todos los logs
        'next_round_due_time': next_round_due_time,
    }
    
    return render(request, 'operator_dashboard.html', context)
    active_shift = get_active_shift(request.user)
    
    progress_tasks = {}
    completed_tasks_count = 0
    total_tasks = 3 

    if active_shift and active_shift.actual_start_time:
        # ... (La lógica de Rondas y Bitácora no cambia) ...
        total_rondas_requeridas = 7
        rondas_completadas = VirtualRoundLog.objects.filter(operator_shift=active_shift).count()
        rondas_completas = rondas_completadas >= total_rondas_requeridas
        progress_tasks['rondas'] = {
            'completed': rondas_completas,
            'text': f"Realizar Rondas Virtuales ({rondas_completadas}/{total_rondas_requeridas})"
        }
        if rondas_completas:
            completed_tasks_count += 1

        empresas_con_instalaciones = Company.objects.filter(installations__isnull=False).distinct()
        total_empresas_requeridas = empresas_con_instalaciones.count()
        ids_empresas_con_log = UpdateLog.objects.filter(operator_shift=active_shift).values_list('installation__company_id', flat=True).distinct()
        bitacora_completa = len(ids_empresas_con_log) >= total_empresas_requeridas
        progress_tasks['bitacora'] = {
            'completed': bitacora_completa,
            'text': f"Anotar en Bitácora ({len(ids_empresas_con_log)}/{total_empresas_requeridas} empresas)"
        }
        if bitacora_completa:
            completed_tasks_count += 1

        # --- INICIO DE LA SECCIÓN CORREGIDA ---
        
        # 3. Validación estricta de Correos (un correo por cada empresa)
        # Se elimina el filtro .filter(is_active=True)
        todas_las_empresas = Company.objects.all() 
        total_empresas_correo = todas_las_empresas.count()
        ids_empresas_con_correo = Email.objects.filter(
            operator=request.user, 
            created_at__gte=active_shift.actual_start_time
        ).values_list('company_id', flat=True)
        correos_completos = len(ids_empresas_con_correo) >= total_empresas_correo
        progress_tasks['correos'] = {
            'completed': correos_completos,
            'text': f"Enviar Correos de Novedades ({len(ids_empresas_con_correo)}/{total_empresas_correo} empresas)"
        }
        if correos_completos:
            completed_tasks_count += 1
            
    progress_percentage = int((completed_tasks_count / total_tasks) * 100) if total_tasks > 0 else 0
    
    # --- FIN DE LA SECCIÓN CORREGIDA ---

    # El resto de la función no cambia...
    pending_checklist_items = []
    if active_shift and active_shift.actual_start_time:
        completed_in_shift_ids = ChecklistLog.objects.filter(operator_shift=active_shift).values_list('item_id', flat=True)
        pending_items = ChecklistItem.objects.exclude(id__in=completed_in_shift_ids)
        for item in pending_items:
            pending_checklist_items.append({
                'description': item.description,
                'offset_minutes': item.trigger_offset_minutes
            })

    # --- INICIO MEJORA #4 Y #7 ---
    processed_logs = []
    if active_shift and active_shift.actual_start_time:
        # 1. Obtener TODOS los logs del turno actual
        traceability_logs_qs = TraceabilityLog.objects.filter(
            user=request.user,
            timestamp__gte=active_shift.actual_start_time
        ).order_by('-timestamp')

        # 2. Procesar cada log para formatear la duración
        for log in traceability_logs_qs:
            action_text = log.action
            # Buscar el patrón de duración en el texto de la acción
            match = re.search(r'Duración: (\d+)s', log.action)
            if match:
                seconds = int(match.group(1))
                if seconds < 60:
                    formatted_duration = f"{seconds} segundos"
                elif seconds < 3600:
                    minutes = seconds // 60
                    rem_seconds = seconds % 60
                    formatted_duration = f"{minutes} min {rem_seconds} seg"
                else:
                    hours = seconds // 3600
                    rem_minutes = (seconds % 3600) // 60
                    formatted_duration = f"{hours}h {rem_minutes} min"
                
                # Reemplazar la duración original con la formateada
                action_text = log.action.replace(f"Duración: {seconds}s", f"Duración: {formatted_duration}")

            processed_logs.append({'action': action_text, 'timestamp': log.timestamp})
    
    else:
        # Si no hay turno activo, la lista de logs está vacía
        processed_logs = []
    # --- FIN MEJORA #4 Y #7 ---

    context = {
        'active_shift': active_shift,
        'progress_tasks': progress_tasks,
        'progress_percentage': progress_percentage,
        'active_round_id': request.session.get('active_round_id'),
        'pending_checklist_json': json.dumps(pending_checklist_items),
        'traceability_logs': processed_logs, # Usar la lista procesada
    }
    
    return render(request, 'operator_dashboard.html', context)


@login_required
def start_shift(request):
    """
    Vista que maneja la ACCIÓN de iniciar un turno.
    """
    if request.method == 'POST':
        # Busca el turno asignado más próximo que aún no ha comenzado.
        # Es la lógica más segura para evitar iniciar un turno equivocado.
        shift_to_start = OperatorShift.objects.filter(
            operator=request.user,
            actual_start_time__isnull=True,
            actual_end_time__isnull=True
        ).order_by('date', 'shift_type__start_time').first()

        if shift_to_start:
            shift_to_start.actual_start_time = timezone.now()
            shift_to_start.save()
            messages.success(request, f"Turno '{shift_to_start.shift_type.name}' iniciado correctamente.")
        else:
            messages.error(request, "No se pudo encontrar un turno pendiente para iniciar.")

    return redirect('operator_dashboard')


    if request.method == 'POST':
        today = timezone.now().date()
        # Busca un turno asignado para hoy que aún no haya comenzado
        active_shift = OperatorShift.objects.filter(
            operator=request.user,
            date=today,
            actual_start_time__isnull=True
        ).first()

        if active_shift:
            active_shift.actual_start_time = timezone.now()
            active_shift.save()
            TraceabilityLog.objects.create(user=request.user, action="Inició turno.")

    return redirect('operator_dashboard')


@login_required
def update_log_view(request):
    """
    Vista corregida y funcional para tu bitácora de tarjetas.
    """
    # 1. Validamos que el turno esté activo.
    active_shift = get_active_shift(request.user)
    if not active_shift or not active_shift.actual_start_time:
        messages.error(request, "Debes iniciar un turno activo para registrar novedades.")
        return redirect('operator_dashboard')

    # 2. Manejamos el guardado del formulario cuando se envía.
    if request.method == 'POST':
        form = UpdateLogForm(request.POST)
        if form.is_valid():
            new_log = form.save(commit=False)
            new_log.operator_shift = active_shift
            new_log.save()
            messages.success(request, 'Novedad registrada con éxito en la bitácora.')
            return redirect('operator_dashboard')
        else:
            # Si el formulario no es válido, mostramos los errores.
            messages.error(request, 'Hubo un error al guardar la novedad. Por favor, revisa los datos.')

    # 3. Preparamos los datos para mostrar la página por primera vez (GET).
    form = UpdateLogForm()
    
    # Esta es la línea clave que faltaba:
    # Obtenemos todas las empresas y le decimos a Django que también cargue
    # todas sus instalaciones relacionadas en una sola consulta eficiente.
    companies_with_installations = Company.objects.prefetch_related('installations')

    context = {
        'form': form,
        'companies': companies_with_installations # Le pasamos las empresas a tu plantilla
    }
    
    return render(request, 'update_log.html', context)
    """
    Vista completa y funcional para registrar una novedad en la bitácora.
    """
    # 1. Usamos la función robusta para obtener el turno activo.
    active_shift = get_active_shift(request.user)

    # 2. Validamos que el turno exista y que ya haya comenzado.
    #    Si no, redirigimos con un mensaje de error.
    if not active_shift or not active_shift.actual_start_time:
        messages.error(request, "Debes iniciar un turno activo para poder registrar novedades.")
        return redirect('operator_dashboard')

    # 3. Manejamos el envío del formulario (petición POST).
    if request.method == 'POST':
        form = UpdateLogForm(request.POST)
        if form.is_valid():
            # Creamos la entrada pero no la guardamos aún...
            new_log = form.save(commit=False)
            # ...porque necesitamos añadirle el turno activo del operador.
            new_log.operator_shift = active_shift
            new_log.save() # Ahora sí la guardamos.
            
            messages.success(request, 'Novedad registrada con éxito.')
            return redirect('operator_dashboard') # Redirigimos al panel.
    else:
        # 4. Si es la primera vez que se carga la página (petición GET),
        #    creamos un formulario vacío.
        form = UpdateLogForm()

    # 5. Preparamos el contexto con el formulario y renderizamos la plantilla.
    context = {
        'form': form
    }
    return render(request, 'update_log.html', context)

@login_required
def checklist_view(request):
    """
    Vista final para el checklist, compatible con la plantilla de acordeón.
    """
    active_shift = get_active_shift(request.user)

    if not active_shift or not active_shift.actual_start_time:
        messages.error(request, "Debes iniciar un turno activo para ver el checklist.")
        return redirect('operator_dashboard')

    # Manejo del guardado de tareas (petición POST)
    if request.method == 'POST':
        completed_item_ids = request.POST.getlist('items') # Tu HTML usa name="items"
        for item_id in completed_item_ids:
            ChecklistLog.objects.get_or_create(
                operator_shift=active_shift,
                item_id=item_id
            )
        messages.success(request, "Checklist actualizado con éxito.")
        return redirect('operator_dashboard')

    # Lógica para preparar los datos para tu plantilla (petición GET)
    completed_ids = ChecklistLog.objects.filter(
        operator_shift=active_shift
    ).values_list('item_id', flat=True)

    # Creamos un diccionario ordenado para mantener la secuencia del turno
    checklist_data = OrderedDict([
        ('Inicio de Turno', []),
        ('Durante el Turno', []),
        ('Finalización de Turno', [])
    ])

    # Llenamos el diccionario con las tareas correspondientes
    for item in ChecklistItem.objects.all():
        phase_text = item.get_phase_display()
        if phase_text in checklist_data:
            checklist_data[phase_text].append(item)

    # Eliminamos las secciones del acordeón que no tengan tareas
    final_checklist_data = {
        phase: items for phase, items in checklist_data.items() if items
    }

    context = {
        'checklist_data': final_checklist_data,
        'completed_ids': list(completed_ids),
        'active_shift': active_shift
    }
    
    return render(request, 'checklist.html', context)
    """
    Vista robusta para mostrar y gestionar las tareas del checklist.
    """
    # 1. Usamos la función robusta para obtener el turno.
    active_shift = get_active_shift(request.user)

    # 2. Validamos que el turno exista y haya comenzado.
    if not active_shift or not active_shift.actual_start_time:
        messages.error(request, "Debes iniciar un turno activo para ver el checklist.")
        return redirect('operator_dashboard')

    # 3. Si el turno es válido, procedemos a obtener las tareas.
    
    # Calculamos el tiempo transcurrido desde el inicio del turno en minutos.
    time_since_shift_start = (timezone.now() - active_shift.actual_start_time).total_seconds() / 60
    
    # Obtenemos las tareas que ya deberían estar disponibles según el tiempo transcurrido.
    available_items = ChecklistItem.objects.filter(
        trigger_offset_minutes__lte=time_since_shift_start
    )

    # Obtenemos los IDs de las tareas que ya fueron completadas en ESTE turno.
    completed_items_ids = ChecklistLog.objects.filter(operator_shift=active_shift).values_list('item_id', flat=True)
    
    # Filtramos para obtener solo las tareas que están disponibles pero aún no se han completado.
    pending_items = available_items.exclude(id__in=completed_items_ids)

    # 4. Manejamos el guardado de las tareas completadas (acción POST).
    if request.method == 'POST':
        # Obtenemos la lista de IDs de los items marcados como completados desde el formulario.
        items_to_log_ids = request.POST.getlist('items_completed')
        
        for item_id in items_to_log_ids:
            # Creamos un registro en ChecklistLog para cada tarea completada.
            ChecklistLog.objects.create(
                operator_shift=active_shift,
                item_id=item_id
            )
        
        messages.success(request, "Checklist actualizado con éxito.")
        return redirect('operator_dashboard') # Redirigimos para un mejor flujo.

    # 5. Preparamos el contexto y renderizamos la plantilla.
    context = {
        'pending_items': pending_items,
        'active_shift': active_shift
    }
    
    return render(request, 'checklist.html', context)
    

    # Buscamos el turno activo del operador para hoy
    active_shift = OperatorShift.objects.filter(
        operator=request.user,
        date=timezone.now().date()
    ).first()

    if not active_shift:
        # Si no tiene turno, no puede registrar novedades
        return redirect('operator_dashboard')

    if request.method == 'POST':
        form = UpdateLogForm(request.POST)
        if form.is_valid():
            log = form.save(commit=False)
            # --- ESTA ES LA LÍNEA CLAVE QUE FALTABA ---
            # Asignamos el turno activo al nuevo registro de novedad.
            log.operator_shift = active_shift

            log.save()
            TraceabilityLog.objects.create(user=request.user, action=f"Registró novedad para {log.installation}")
            return redirect('operator_dashboard')
    else:
        form = UpdateLogForm()

    companies_with_installations = Company.objects.prefetch_related('installations')

    context = {
        'form': form,
        'companies': companies_with_installations
    }
    return render(request, 'update_log.html', context)

@login_required
def email_form_view(request):
    if not get_active_shift(request.user): return redirect('operator_dashboard')
    if request.method == 'POST':
        form = EmailForm(request.POST)
        if form.is_valid():
            email = form.save(commit=False); email.operator = request.user; email.status = 'pending'; email.save()
            form.save_m2m()
            TraceabilityLog.objects.create(user=request.user, action=f"Generó borrador de correo para {email.company.name}")
            return redirect('operator_dashboard')
    else: form = EmailForm()
    return render(request, 'email_form.html', {'form': form})

# Flujo de Rondas Virtuales


@login_required
def end_turn_preview(request):
    active_shift = get_active_shift(request.user)
    if not active_shift or not active_shift.actual_start_time:
        messages.error(request, "No tienes un turno activo o iniciado.")
        return redirect('operator_dashboard')

    # ... (toda tu lógica de validación se mantiene igual) ...
    validation_errors = []
    total_rondas_requeridas = 7
    rondas_completadas = VirtualRoundLog.objects.filter(operator_shift=active_shift).count()
    if rondas_completadas < total_rondas_requeridas:
        faltantes = total_rondas_requeridas - rondas_completadas
        validation_errors.append(f"Faltan {faltantes} rondas virtuales por completar.")

    empresas_con_instalaciones = Company.objects.filter(installations__isnull=False).distinct()
    ids_empresas_con_log = UpdateLog.objects.filter(operator_shift=active_shift).values_list('installation__company_id', flat=True).distinct()
    empresas_faltantes_bitacora = [c.name for c in empresas_con_instalaciones if c.id not in ids_empresas_con_log]
    if empresas_faltantes_bitacora:
        validation_errors.append(f"Falta registrar en bitácora para: {', '.join(empresas_faltantes_bitacora)}.")

    todas_las_empresas = Company.objects.all()
    ids_empresas_con_correo = Email.objects.filter(operator=request.user, created_at__gte=active_shift.actual_start_time).values_list('company_id', flat=True)
    empresas_faltantes_correo = [c.name for c in todas_las_empresas if c.id not in ids_empresas_con_correo]
    if empresas_faltantes_correo:
        validation_errors.append(f"Falta generar correo para: {', '.join(empresas_faltantes_correo)}.")
        
    if validation_errors:
        full_error_message = "No puedes finalizar el turno. Tareas pendientes: " + " ".join(validation_errors)
        messages.error(request, full_error_message)
        return redirect('operator_dashboard')

    # --- 👇 EL ÚNICO CAMBIO ESTÁ EN LA SIGUIENTE LÍNEA 👇 ---
    # Le decimos a la base de datos que ordene los datos ANTES de enviarlos a la plantilla.
    updates_log = UpdateLog.objects.filter(
        operator_shift=active_shift
    ).select_related('installation__company').order_by(
        'installation__company__name', 'installation__name', 'created_at'
    )
    # --- 👆 FIN DEL CAMBIO 👆 ---

    completed_checklist = ChecklistLog.objects.filter(operator_shift=active_shift).select_related('item')
    rondas_virtuales = VirtualRoundLog.objects.filter(operator_shift=active_shift)

    context = {
        'operator': request.user,
        'start_time': active_shift.actual_start_time,
        'end_time': timezone.now(),
        'completed_checklist': completed_checklist,
        'updates_log': updates_log,  # La plantilla PDF ya usa esta variable
        'rondas_virtuales': rondas_virtuales,
    }

    template = get_template('turn_report_pdf.html')
    html = template.render(context)
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html.encode("UTF-8")), result)

    if not pdf.err:
        report, created = TurnReport.objects.get_or_create(
            operator_shift=active_shift,
            defaults={'operator': request.user, 'start_time': active_shift.actual_start_time}
        )
        pdf_file = ContentFile(result.getvalue())
        report.pdf_report.save(f'reporte_turno_{request.user.username}_{timezone.now().strftime("%Y%m%d")}.pdf', pdf_file, save=True)
        return redirect('sign_turn_report', report_id=report.id)

    messages.error(request, f"Error al generar el PDF: {pdf.err}")
    return redirect('operator_dashboard')


@login_required
def start_virtual_round(request):
    """
    Inicia una nueva ronda virtual.
    Maneja tanto peticiones AJAX (desde el modal) como POST directas (desde el botón manual).
    """
    # Verificamos si la petición es AJAX (del modal) o normal (del botón)
    is_ajax = "application/json" in request.headers.get('Content-Type', '')

    if request.method == 'POST':
        active_shift = get_active_shift(request.user)
        
        # Lógica para prevenir rondas duplicadas
        if 'active_round_id' in request.session:
            message = 'Ya hay una ronda virtual en curso.'
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': message}, status=400)
            messages.warning(request, message)
            return redirect('operator_dashboard')

        # Lógica para iniciar la ronda
        if active_shift and active_shift.actual_start_time:
            new_round = VirtualRoundLog.objects.create(
                operator_shift=active_shift,
                start_time=timezone.now()
            )
            request.session['active_round_id'] = new_round.id
            message = 'Ronda virtual iniciada con éxito.'
            
            if is_ajax:
                return JsonResponse({'status': 'success', 'round_id': new_round.id})
            messages.success(request, message)
            return redirect('operator_dashboard')

    # Si algo falla (no es POST o no hay turno)
    message = 'No se pudo iniciar la ronda. No hay un turno activo.'
    if is_ajax:
        return JsonResponse({'status': 'error', 'message': message}, status=400)
    messages.error(request, message)
    return redirect('operator_dashboard')

@login_required
def finish_virtual_round(request, round_id):
    # Se busca la ronda por su ID y asegurando que pertenezca al turno del operador
    active_round = get_object_or_404(VirtualRoundLog, id=round_id, operator_shift__operator=request.user)
    if request.method == 'POST':
        form = VirtualRoundCompletionForm(request.POST, instance=active_round) # Se pasa la instancia para la validación
        if form.is_valid():
            installations = form.cleaned_data['checked_installations']
            active_round.checked_installations = ", ".join([inst.name for inst in installations])
            end_time = timezone.now()
            duration = end_time - active_round.start_time
            active_round.end_time = end_time
            active_round.duration_seconds = duration.total_seconds()
            active_round.save()
            TraceabilityLog.objects.create(user=request.user, action=f"Finalizó ronda virtual. Duración: {int(duration.total_seconds())}s.")
            if 'active_round_id' in request.session: del request.session['active_round_id']
            return redirect('operator_dashboard')
    else:
        form = VirtualRoundCompletionForm() # No se necesita la instancia aquí, solo para el POST
    return render(request, 'finish_virtual_round.html', {'form': form, 'round': active_round})


# Flujo de Reporte de Turno

    active_shift = OperatorShift.objects.filter(
        operator=request.user,
        date=timezone.now().date()
    ).first()

    if not active_shift:
        return redirect('operator_dashboard') # No puede finalizar un turno que no existe

    # Recolectamos datos filtrando por el turno activo
    completed_checklist = ChecklistLog.objects.filter(operator_shift=active_shift)
    updates_log = UpdateLog.objects.filter(operator_shift=active_shift)
    rondas_virtuales = VirtualRoundLog.objects.filter(operator_shift=active_shift)

    # Excluimos las rondas del checklist general para no duplicar
    ronda_item = ChecklistItem.objects.filter(description__icontains="ronda virtual").first()
    if ronda_item:
        completed_checklist = completed_checklist.exclude(item=ronda_item)

    context = {
        'operator': request.user,
        'start_time': active_shift.actual_start_time,
        'end_time': timezone.now(),
        'completed_checklist': completed_checklist,
        'updates_log': updates_log,
        'rondas_virtuales': rondas_virtuales,
    }

    # ... (El resto de la lógica para generar el PDF sigue igual que antes) ...
    template = get_template('turn_report_pdf.html')
    html = template.render(context)
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html.encode("UTF-8")), result)

    if not pdf.err:
        report = TurnReport(operator=request.user, start_time=active_shift.actual_start_time)
        report.pdf_report.save(f'reporte_turno_{request.user.username}_{timezone.now().strftime("%Y%m%d%H%M%S")}.pdf', ContentFile(result.getvalue()))
        active_shift.actual_end_time = timezone.now()
        active_shift.save()
        report.save()
        return redirect('sign_turn_report', report_id=report.id)

    return HttpResponse("Error al generar el PDF", status=500)

@login_required
def sign_turn_report(request, report_id):
    report = get_object_or_404(TurnReport, id=report_id, operator=request.user)

    # Buscamos el turno activo asociado a este reporte
    active_shift = get_active_shift(request.user)

    if request.method == 'POST':
        # 1. Marca el reporte como firmado
        report.is_signed = True
        report.signed_at = timezone.now()
        report.save()

        # 2. --- ESTA ES LA LÓGICA CLAVE QUE FALTABA ---
        #    Marca el turno como finalizado
        if active_shift:
            active_shift.actual_end_time = timezone.now()
            active_shift.save()

        TraceabilityLog.objects.create(user=request.user, action="Firmó y finalizó su reporte de turno.")

        # 3. Cierra la sesión del usuario
        logout(request)
        return redirect('login')

    return render(request, 'turn_report_preview.html', {'report': report})

# --- VISTAS AJAX ---
@login_required
def get_updates_for_company(request, company_id):
    # Obtenemos el turno activo del operador que hace la petición
    active_shift = get_active_shift(request.user)
    if not active_shift:
        return JsonResponse({'grouped_updates': []})

    # Buscamos instalaciones de la empresa que tengan novedades DE ESTE TURNO
    installations_with_updates = Installation.objects.filter(
        company_id=company_id,
        updatelog__operator_shift=active_shift
    ).distinct()

    response_data = []
    for installation in installations_with_updates:
        # Filtramos las novedades por instalación Y por el turno activo
        updates = UpdateLog.objects.filter(
            installation=installation,
            operator_shift=active_shift
        ).order_by('-created_at')

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
    """
    Vista de API que le dice al frontend si debe mostrar una alarma.
    """
    active_shift = get_active_shift(request.user)
    
    response_data = {
        'pending_checklist': False,
        'pending_round': False
    }

    # Si no hay turno o no ha empezado, no hay alarmas que mostrar.
    if not active_shift or not active_shift.actual_start_time:
        return JsonResponse(response_data)

    # Lógica para verificar si hay tareas de checklist pendientes
    # Comparamos la cantidad de tareas que existen con las que se han completado.
    total_items_count = ChecklistItem.objects.count()
    completed_items_count = ChecklistLog.objects.filter(operator_shift=active_shift).count()

    if total_items_count > completed_items_count:
        response_data['pending_checklist'] = True

    # Aquí irá la futura lógica para la alarma de la ronda virtual
    
    return JsonResponse(response_data)
    """
    Vista de API para que el frontend consulte si hay alarmas pendientes.
    """
    current_shift = OperatorShift.objects.filter(operator=request.user, actual_end_time__isnull=True).first()
    
    response_data = {
        'pending_checklist': False,
        'pending_round': False
    }

    if current_shift:
        # Lógica para verificar checklist pendiente
        now = timezone.now()
        time_since_shift_start = (now - current_shift.actual_start_time).total_seconds() / 60
        
        available_items_count = ChecklistItem.objects.filter(trigger_offset_minutes__lte=time_since_shift_start).count()
        completed_items_count = ChecklistLog.objects.filter(operator_shift=current_shift).count()

        if available_items_count > completed_items_count:
            response_data['pending_checklist'] = True

        # Lógica para verificar ronda virtual (la implementaremos completamente más adelante)
        # Por ahora, es un ejemplo. Podríamos basarlo en la última ronda.
        last_round = VirtualRoundLog.objects.filter(operator_shift=current_shift).order_by('-start_time').first()
        if not last_round:
            # Si nunca ha hecho una ronda, podría ser una alarma
            pass # Aquí iría la lógica de cuándo debe ser la primera ronda
        else:
            # Si ya hizo una, la siguiente podría ser X tiempo después
            pass # Lógica para rondas periódicas

    return JsonResponse(response_data)

@csrf_exempt # Deshabilitamos CSRF para esta vista AJAX
@login_required
@user_passes_test(is_supervisor)
@transaction.atomic # Asegura que todos los cambios se hagan correctamente o ninguno
def update_checklist_order(request):
    if request.method == 'POST':
        try:
            # Cargamos la lista de IDs desde el cuerpo de la petición
            data = json.loads(request.body)
            item_ids = data.get('order', [])
            
            # Recorremos la lista de IDs. El índice nos da el nuevo orden.
            for index, item_id in enumerate(item_ids):
                ChecklistItem.objects.filter(pk=item_id).update(order=index)
                
            return JsonResponse({'status': 'success', 'message': 'Orden actualizado correctamente.'})
        except Exception as e:
            # Si algo sale mal, devolvemos un error
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    
    return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=405)