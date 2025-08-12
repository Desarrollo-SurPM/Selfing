# desarrollo-surpm/selfing/Selfing-mejorasorden/core/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.template.loader import get_template
from xhtml2pdf import pisa
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.db.models import Q, Count
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
    UpdateLogForm, OperatorCreationForm,
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
    
    operadores_en_turno = OperatorShift.objects.filter(
        date=today,
        actual_start_time__isnull=False,
        actual_end_time__isnull=True
    ).count()

    novedades_hoy = UpdateLog.objects.filter(created_at__date=today).count()
    
    # --- CAMBIO: Se reemplaza correos pendientes por reportes finalizados ---
    reportes_finalizados_count = TurnReport.objects.filter(is_signed=True, signed_at__date=today).count()
    
    servicios_monitoreados_activos = MonitoredService.objects.filter(is_active=True).count()
    traceability_logs = TraceabilityLog.objects.select_related('user').all().order_by('-timestamp')[:6]
    reports = UpdateLog.objects.filter(created_at__date=today).select_related(
        'operator_shift__operator', 'installation__company'
    ).order_by('-created_at')

    context = {
        'novedades_hoy': novedades_hoy,
        'reportes_finalizados_count': reportes_finalizados_count, # Nuevo dato para la plantilla
        'operadores_en_turno': operadores_en_turno,
        'servicios_monitoreados_activos': servicios_monitoreados_activos,
        'reports': reports,
        'traceability_logs': traceability_logs,
    }
    return render(request, 'admin_dashboard.html', context)

@login_required
@user_passes_test(is_supervisor)
def review_and_send_novedades(request):
    company_id = request.GET.get('company_id')
    selected_company = None
    novedades_pendientes = None

    if request.method == 'POST':
        selected_ids = request.POST.getlist('updates_to_send')
        observations = request.POST.get('observations', '')
        company_id_form = request.POST.get('company_id')

        if not selected_ids:
            messages.warning(request, "Debe seleccionar al menos una novedad para enviar.")
            return redirect(f"{request.path_info}?company_id={company_id_form}")

        company = get_object_or_404(Company, id=company_id_form)
        updates = UpdateLog.objects.filter(id__in=selected_ids).order_by('installation__name', 'created_at')

        if company.email:
            try:
                email_context = {
                    'company': company,
                    'updates': updates,
                    'observations': observations,
                    'enviado_por': request.user,
                }
                html_message = render_to_string('emails/reporte_novedades.html', email_context)
                
                send_mail(
                    subject=f"Reporte de Novedades - {company.name} - {timezone.now().strftime('%d/%m/%Y')}",
                    message="",
                    from_email=None,
                    recipient_list=[company.email],
                    fail_silently=False,
                    html_message=html_message
                )
                
                updates.update(is_sent=True)
                TraceabilityLog.objects.create(user=request.user, action=f"Envió correo de novedades a {company.name}.")
                messages.success(request, f"Correo enviado correctamente a {company.name}.")

            except Exception as e:
                messages.error(request, f"Error al enviar el correo: {e}")
                return redirect(f"{request.path_info}?company_id={company_id_form}")
        else:
            messages.warning(request, f"La empresa {company.name} no tiene un correo configurado.")

        return redirect('review_and_send_novedades')

    # --- LÓGICA GET (CUANDO SE CARGA LA PÁGINA) ---
    if company_id:
        selected_company = get_object_or_404(Company, id=company_id)
        novedades_pendientes = UpdateLog.objects.filter(
            installation__company=selected_company, is_sent=False
        ).exclude(
            operator_shift__shift_type__name__iexact='Turno Mañana'
        ).select_related('operator_shift__operator', 'installation').order_by('installation__name', '-created_at')

    companies_with_pending_updates = Company.objects.filter(
        installations__updatelog__is_sent=False
    ).exclude(
        installations__updatelog__operator_shift__shift_type__name__iexact='Turno Mañana'
    ).annotate(
        pending_count=Count('installations__updatelog', filter=Q(installations__updatelog__is_sent=False))
    ).filter(pending_count__gt=0).distinct()

    context = {
        'companies': companies_with_pending_updates,
        'selected_company': selected_company,
        'novedades_pendientes': novedades_pendientes
    }
    # --- LA LÍNEA QUE FALTABA Y SOLUCIONA EL ERROR ---
    return render(request, 'review_and_send.html', context)

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
def operator_dashboard(request):
    active_shift = get_active_shift(request.user)
    
    # Preparamos un contexto base
    context = {'active_shift': active_shift}

    # Si el turno ya ha sido iniciado, calculamos todo el progreso y las tareas.
    if active_shift and active_shift.actual_start_time:
        progress_tasks = {}
        completed_tasks_count = 0
        total_tasks = 3 
        
        # 1. Lógica de Progreso
        total_rondas_requeridas = 7
        rondas_completadas = VirtualRoundLog.objects.filter(operator_shift=active_shift).count()
        progress_tasks['rondas'] = {'completed': (rondas_completadas >= total_rondas_requeridas), 'text': f"Rondas ({rondas_completadas}/{total_rondas_requeridas})"}
        if progress_tasks['rondas']['completed']: completed_tasks_count += 1

        empresas_con_instalaciones = Company.objects.filter(installations__isnull=False).distinct()
        ids_empresas_con_log = UpdateLog.objects.filter(operator_shift=active_shift).values_list('installation__company_id', flat=True).distinct()
        progress_tasks['bitacora'] = {'completed': (len(ids_empresas_con_log) >= empresas_con_instalaciones.count()), 'text': f"Bitácora ({len(ids_empresas_con_log)}/{empresas_con_instalaciones.count()})"}
        if progress_tasks['bitacora']['completed']: completed_tasks_count += 1
        
        todas_las_empresas = Company.objects.all()
        ids_empresas_con_correo = Email.objects.filter(operator=request.user, created_at__gte=active_shift.actual_start_time).values_list('company_id', flat=True)
        progress_tasks['correos'] = {'completed': (len(ids_empresas_con_correo) >= todas_las_empresas.count()), 'text': f"Correos ({len(ids_empresas_con_correo)}/{todas_las_empresas.count()})"}
        if progress_tasks['correos']['completed']: completed_tasks_count += 1
        
        context['progress_percentage'] = int((completed_tasks_count / total_tasks) * 100) if total_tasks > 0 else 0
        context['progress_tasks'] = progress_tasks
        
        # 2. Lógica de Alarma
        applicable_items = get_applicable_checklist_items(active_shift)
        completed_in_shift_ids = ChecklistLog.objects.filter(operator_shift=active_shift).values_list('item_id', flat=True)
        pending_items = applicable_items.exclude(id__in=completed_in_shift_ids)
        pending_alarms_data = []
        for item in pending_items:
            if item.alarm_trigger_delay:
                due_time = active_shift.actual_start_time + item.alarm_trigger_delay
                pending_alarms_data.append({'id': item.id, 'description': item.description, 'due_time': due_time.isoformat()})
        context['pending_alarms_json'] = json.dumps(pending_alarms_data)

        # 3. Lógica de Logs del Turno
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
        
        # 4. Lógica del Temporizador de Rondas
        last_round = VirtualRoundLog.objects.filter(operator_shift=active_shift).order_by('-start_time').first()
        base_time = last_round.start_time if last_round else active_shift.actual_start_time
        context['next_round_due_time'] = (base_time + timedelta(minutes=60)).isoformat()
        
        context['active_round_id'] = request.session.get('active_round_id')

    return render(request, 'operator_dashboard.html', context)

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

def get_applicable_checklist_items(active_shift):
    """
    Obtiene los ítems del checklist que aplican al turno y día actual.
    """
    # --- CORRECCIÓN AQUÍ ---
    # Verificamos 'active_shift.shift_type' en lugar de 'active_shift.shift'
    if not active_shift or not active_shift.shift_type:
        return ChecklistItem.objects.none()

    today_weekday = timezone.now().weekday()  # Lunes=0, Domingo=6
    
    # --- CORRECCIÓN AQUÍ ---
    # Accedemos directamente a 'active_shift.shift_type'
    current_shift_type = active_shift.shift_type

    # Filtro por tipo de turno:
    turnos_filter = Q(turnos_aplicables=current_shift_type) | Q(turnos_aplicables__isnull=True)

    # Filtro por día de la semana:
    dias_filter = Q(dias_aplicables__contains=str(today_weekday)) | Q(dias_aplicables__isnull=True) | Q(dias_aplicables='')

    return ChecklistItem.objects.filter(turnos_filter, dias_filter).distinct()


    active_shift = get_active_shift(request.user)
    
    # Valores iniciales
    progress_tasks = {}
    completed_tasks_count = 0
    total_tasks = 3 
    next_round_due_time = None
    pending_alarms_data = [] # Para las alarmas
    processed_logs = [] # Para el historial
    progress_percentage = 0

    if active_shift and active_shift.actual_start_time:
        # --- 1. Lógica de Progreso (Tu código, sin cambios) ---
        total_rondas_requeridas = 7
        rondas_completadas = VirtualRoundLog.objects.filter(operator_shift=active_shift).count()
        progress_tasks['rondas'] = {'completed': (rondas_completadas >= total_rondas_requeridas), 'text': f"Realizar Rondas Virtuales ({rondas_completadas}/{total_rondas_requeridas})"}
        if progress_tasks['rondas']['completed']: completed_tasks_count += 1

        empresas_con_instalaciones = Company.objects.filter(installations__isnull=False).distinct()
        ids_empresas_con_log = UpdateLog.objects.filter(operator_shift=active_shift).values_list('installation__company_id', flat=True).distinct()
        progress_tasks['bitacora'] = {'completed': (len(ids_empresas_con_log) >= empresas_con_instalaciones.count()), 'text': f"Anotar en Bitácora ({len(ids_empresas_con_log)}/{empresas_con_instalaciones.count()})"}
        if progress_tasks['bitacora']['completed']: completed_tasks_count += 1
        
        todas_las_empresas = Company.objects.all()
        ids_empresas_con_correo = Email.objects.filter(operator=request.user, created_at__gte=active_shift.actual_start_time).values_list('company_id', flat=True)
        progress_tasks['correos'] = {'completed': (len(ids_empresas_con_correo) >= todas_las_empresas.count()), 'text': f"Enviar Correos ({len(ids_empresas_con_correo)}/{todas_las_empresas.count()})"}
        if progress_tasks['correos']['completed']: completed_tasks_count += 1
        
        progress_percentage = int((completed_tasks_count / total_tasks) * 100) if total_tasks > 0 else 0
        
        # --- 2. Lógica de Alarma (Usando el nuevo filtrado) ---
        applicable_items = get_applicable_checklist_items(active_shift)
        completed_in_shift_ids = ChecklistLog.objects.filter(operator_shift=active_shift).values_list('item_id', flat=True)
        pending_items = applicable_items.exclude(id__in=completed_in_shift_ids)

        for item in pending_items:
            if item.alarm_trigger_delay:
                due_time = active_shift.actual_start_time + item.alarm_trigger_delay
                pending_alarms_data.append({
                    'id': item.id,
                    'description': item.description,
                    'due_time': due_time.isoformat()
                })

        # --- 3. Lógica para obtener los logs del turno (Tu código, sin cambios) ---
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
        
        # --- 4. Lógica del Temporizador de Rondas (Tu código, sin cambios) ---
        last_round = VirtualRoundLog.objects.filter(operator_shift=active_shift).order_by('-start_time').first()
        base_time = last_round.start_time if last_round else active_shift.actual_start_time
        next_round_due_time = (base_time + timedelta(minutes=60)).isoformat()
        
    context = {
        'active_shift': active_shift,
        'progress_tasks': progress_tasks,
        'progress_percentage': progress_percentage,
        'active_round_id': request.session.get('active_round_id'),
        'traceability_logs': processed_logs,
        'next_round_due_time': next_round_due_time,
        # **Importante**: Se pasa el JSON correcto para las alarmas
        'pending_alarms_json': json.dumps(pending_alarms_data), 
    }
    
    return render(request, 'operator_dashboard.html', context)



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
    active_shift = get_active_shift(request.user)

    if not active_shift:
        return redirect('operator_dashboard')

    if request.method == 'POST':
        selected_item_ids = request.POST.getlist('items')
        for item_id in selected_item_ids:
            if not ChecklistLog.objects.filter(item_id=item_id, operator_shift=active_shift).exists():
                item = ChecklistItem.objects.get(id=item_id)
                observacion = request.POST.get(f'observacion_{item_id}', '')
                ChecklistLog.objects.create(item=item, operator_shift=active_shift, observacion=observacion)
        
        # --- CAMBIO AQUÍ ---
        # --- CAMBIO AQUÍ ---
                # 2. Crea un registro en el historial de "Actividad Reciente".
                TraceabilityLog.objects.create(
                    user=request.user,
                    action=f"Tarea de checklist completada: '{item.description}'"
                )
        # Redirigir al panel de operador después de guardar.
        return redirect('operator_dashboard')

    # --- Lógica para la petición GET (sin cambios) ---
    checklist_items = get_applicable_checklist_items(active_shift)
    completed_logs_dict = {log.item.id: log for log in ChecklistLog.objects.filter(operator_shift=active_shift)}

    tasks_for_js = [
        {
            'id': item.id,
            'description': item.description,
            'completed': bool(completed_logs_dict.get(item.id)),
            'observation': completed_logs_dict.get(item.id).observacion if completed_logs_dict.get(item.id) else ''
        }
        for item in checklist_items
    ]

    context = {
        'checklist_items': checklist_items,
        'completed_logs_dict': completed_logs_dict,
        'tasks_for_js': tasks_for_js,
    }
    return render(request, 'checklist.html', context)
    active_shift = OperatorShift.objects.filter(operator=request.user, actual_end_time__isnull=True).first()

    if not active_shift:
        return redirect('operator_dashboard')

    if request.method == 'POST':
        selected_item_ids = request.POST.getlist('items')
        for item_id in selected_item_ids:
            # Solo procesamos ítems que no hayan sido ya registrados en este turno.
            if not ChecklistLog.objects.filter(item_id=item_id, operator_shift=active_shift).exists():
                item = ChecklistItem.objects.get(id=item_id)
                observacion = request.POST.get(f'observacion_{item_id}', '')
                ChecklistLog.objects.create(
                    item=item,
                    operator_shift=active_shift,
                    observacion=observacion
                )
        return redirect('checklist')

    # --- Lógica de GET Actualizada ---
    # Usamos la misma función para obtener los ítems que aplican al turno.
    checklist_items = get_applicable_checklist_items(active_shift)
    
    completed_logs = ChecklistLog.objects.filter(operator_shift=active_shift)
    completed_logs_dict = {log.item.id: log for log in completed_logs}

    tasks_for_js = []
    for item in checklist_items:
        log = completed_logs_dict.get(item.id)
        tasks_for_js.append({
            'id': item.id,
            'description': item.description,
            'completed': bool(log),
            'observation': log.observacion if log else ''
        })

    context = {
        'checklist_items': checklist_items,
        'completed_logs_dict': completed_logs_dict,
        'tasks_for_js': tasks_for_js,
    }
    return render(request, 'checklist.html', context)



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

@login_required
def check_pending_alarms(request):
    """
    NUEVA LÓGICA DE ALARMAS:
    Esta vista ahora devuelve las tareas específicas que están vencidas.
    """
    active_shift = get_active_shift(request.user)
    overdue_tasks = []

    if active_shift and active_shift.actual_start_time:
        now = timezone.now()
        
        # 1. Obtiene solo los ítems que aplican a este turno específico.
        applicable_items = get_applicable_checklist_items(active_shift)
        
        # 2. Obtiene los IDs de las tareas ya completadas en este turno.
        completed_item_ids = ChecklistLog.objects.filter(
            operator_shift=active_shift
        ).values_list('item_id', flat=True)
        
        # 3. Filtra para quedarse solo con las tareas pendientes que tienen alarma.
        pending_items_with_alarm = applicable_items.exclude(
            id__in=completed_item_ids
        ).filter(
            alarm_trigger_delay__isnull=False
        )
        
        # 4. Comprueba si alguna de las tareas pendientes está vencida.
        for item in pending_items_with_alarm:
            due_time = active_shift.actual_start_time + item.alarm_trigger_delay
            if now > due_time:
                overdue_tasks.append({'description': item.description})

    return JsonResponse({'overdue_tasks': overdue_tasks})

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