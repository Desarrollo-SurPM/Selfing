# desarrollo-surpm/selfing/Selfing-mejorasorden/core/views.py
from django.db.models import Min, Max
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.template.loader import get_template
from xhtml2pdf import pisa
from .utils import link_callback
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.db.models import Q, Count
from collections import defaultdict
from django.contrib import messages
from io import BytesIO
from django.db import transaction
from django.core.files.base import ContentFile
from django import forms
from datetime import timedelta, datetime, time
from collections import defaultdict
from django.contrib.auth import logout
from collections import OrderedDict
import json
from django.views.decorators.csrf import csrf_exempt 
import re # Importar el módulo de expresiones regulares
from django.db.models.functions import Coalesce
from django.db.models import TimeField

from .models import (
    Company, Installation, OperatorProfile, ShiftType, OperatorShift,
    ChecklistItem, ChecklistLog, VirtualRoundLog, UpdateLog, Email, EmergencyContact,
    TurnReport, MonitoredService, ServiceStatusLog, TraceabilityLog, ShiftNote,
    Vehicle, VehiclePosition, VehicleAlert, VehicleRoute
)
from .forms import (
    UpdateLogForm, OperatorCreationForm, ShiftNoteForm,
    OperatorChangeForm, CompanyForm, InstallationForm, ChecklistItemForm, EmergencyContactForm,
    MonitoredServiceForm, ShiftTypeForm, OperatorShiftForm, VirtualRoundCompletionForm, UpdateLogEditForm, AdminUpdateLogForm
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
    """
    Dashboard del administrador con lógica de ciclo operativo corregida
    para mostrar datos desde el último inicio de ciclo (normalmente 08:30 AM).
    """
    ahora = timezone.now()
    
    # --- INICIO DE LA LÓGICA CORREGIDA ---
    # Se determina el inicio del "día operativo" actual. El corte es a las 08:30.
    today_at_8_30 = ahora.replace(hour=8, minute=30, second=0, microsecond=0)

    if ahora.time() < time(8, 30):
        # Si son antes de las 08:30, el ciclo actual comenzó AYER a las 08:30.
        start_of_operational_day = today_at_8_30 - timedelta(days=1)
    else:
        # Si son después de las 08:30, el ciclo actual comenzó HOY a las 08:30.
        start_of_operational_day = today_at_8_30
    # --- FIN DE LA LÓGICA CORREGIDA ---

    # 1. Novedades registradas desde el inicio del ciclo operativo.
    novedades_hoy = UpdateLog.objects.filter(
        created_at__gte=start_of_operational_day
    ).count()
    
    # 2. Reportes finalizados desde el inicio del ciclo operativo.
    reportes_finalizados_count = TurnReport.objects.filter(
        is_signed=True,
        signed_at__gte=start_of_operational_day
    ).count()
    
    # 3. Operadores actualmente en turno (esta lógica está bien).
    operadores_en_turno = OperatorShift.objects.filter(
        actual_start_time__isnull=False,
        actual_end_time__isnull=True
    ).count()

    # El resto de las consultas se mantienen igual.
    servicios_monitoreados_activos = MonitoredService.objects.filter(is_active=True).count()
    traceability_logs = TraceabilityLog.objects.select_related('user').all().order_by('-timestamp')[:6]
    
    # La tabla de "Novedades del Día" también usará el nuevo rango de tiempo.
    reports = UpdateLog.objects.filter(created_at__gte=start_of_operational_day).select_related(
        'operator_shift__operator', 'installation__company'
    ).order_by('-created_at')

    context = {
        'novedades_hoy': novedades_hoy,
        'reportes_finalizados_count': reportes_finalizados_count,
        'operadores_en_turno': operadores_en_turno,
        'servicios_monitoreados_activos': servicios_monitoreados_activos,
        'reports': reports,
        'traceability_logs': traceability_logs,
    }
    return render(request, 'admin_dashboard.html', context)

    today = timezone.now().date()
    
    
    operadores_en_turno = OperatorShift.objects.filter(
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

# selfing/core/views.py
@login_required
@user_passes_test(is_supervisor)
def review_and_send_novedades(request):
    """
    Gestiona el envío de novedades con una vista previa en modal y ordenamiento cronológico corregido.
    """
    start_of_cycle = None
    end_of_cycle = None

    last_night_shift = OperatorShift.objects.filter(
        shift_type__name__icontains='noche',
        actual_end_time__isnull=False
    ).order_by('-actual_end_time').first()

    if not last_night_shift:
        messages.info(request, "Aún no ha finalizado un ciclo de turnos (noche) para generar un reporte.")
        return render(request, 'review_and_send.html', {'companies': None, 'add_novedad_form': AdminUpdateLogForm()})

    end_of_cycle = last_night_shift.actual_end_time

    shift_before_night = OperatorShift.objects.filter(
        actual_end_time__isnull=False,
        actual_end_time__lte=last_night_shift.actual_start_time
    ).order_by('-actual_end_time').first()

    if not shift_before_night:
        start_of_cycle = last_night_shift.actual_start_time
    else:
        operational_date = shift_before_night.date
        operational_weekday = operational_date.weekday()

        if operational_weekday in [5, 6]:
            shift_before_tarde = OperatorShift.objects.filter(
                actual_end_time__isnull=False,
                actual_end_time__lte=shift_before_night.actual_start_time
            ).order_by('-actual_end_time').first()
            start_of_cycle = shift_before_tarde.actual_start_time if shift_before_tarde else shift_before_night.actual_start_time
        else:
            start_of_cycle = shift_before_night.actual_start_time

    next_shift_after_cycle = OperatorShift.objects.filter(
        actual_start_time__gt=end_of_cycle
    ).order_by('actual_start_time').first()
    
    if next_shift_after_cycle and next_shift_after_cycle.actual_end_time is not None:
        messages.info(request, "El periodo para enviar el reporte del ciclo anterior ha finalizado.")
        return render(request, 'review_and_send.html', {'companies': None, 'add_novedad_form': AdminUpdateLogForm()})

    add_novedad_form = AdminUpdateLogForm()

    if request.method == 'POST':
        if 'action' in request.POST and request.POST['action'] == 'add_novedad':
            form = AdminUpdateLogForm(request.POST)
            if form.is_valid():
                if last_night_shift:
                    new_log = form.save(commit=False)
                    new_log.operator_shift = last_night_shift
                    new_log.save()
                    # Se mantiene tu lógica original para asegurar que la novedad caiga en el ciclo correcto
                    new_log.created_at = end_of_cycle
                    new_log.save(update_fields=['created_at']) 
                    messages.success(request, 'Novedad agregada correctamente al ciclo del reporte.')
                else:
                    messages.error(request, 'No se pudo determinar el turno al cual asociar la novedad.')
                
                company_id_redirect = request.POST.get('company_id_for_redirect', '')
                if company_id_redirect:
                    return redirect(f"{request.path}?company_id={company_id_redirect}")
                return redirect('review_and_send_novedades')
            else:
                messages.error(request, 'Hubo un error al agregar la novedad. Por favor, revisa los datos.')
                add_novedad_form = form
        
        elif 'confirm_send' in request.POST:
            company_id_form = request.POST.get('company_id')
            company = get_object_or_404(Company, id=company_id_form)
            selected_ids = request.POST.getlist('updates_to_send')
            observations = request.POST.get('observations', '')
            
            with transaction.atomic():
                for update_id in selected_ids:
                    new_message = request.POST.get(f'message_{update_id}')
                    if new_message:
                        log_to_update = UpdateLog.objects.get(id=update_id)
                        if log_to_update.message != new_message:
                            log_to_update.message = new_message
                            log_to_update.is_edited = True
                            log_to_update.edited_at = timezone.now()
                            log_to_update.save()
            
            # --- CORRECCIÓN DE ORDENAMIENTO (PARA EL CORREO) ---
            updates_to_send_in_email = UpdateLog.objects.filter(id__in=selected_ids).annotate(
                effective_time=Coalesce('manual_timestamp', 'created_at__time', output_field=TimeField())
            ).order_by('installation__name', 'created_at__date', 'effective_time')
            
            email_string = company.email or ""
            recipient_list = [email.strip() for email in email_string.split(',') if email.strip()]

            if recipient_list:
                try:
                    email_context = {
                        'company': company,
                        'updates': updates_to_send_in_email,
                        'observations': observations,
                        'enviado_por': request.user,
                        'cycle_start': start_of_cycle,
                        'cycle_end': end_of_cycle,
                    }
                    html_message = render_to_string('emails/reporte_novedades.html', email_context)
                    send_mail(
                        subject=f"Reporte de Novedades - {company.name} - {end_of_cycle.strftime('%d/%m/%Y')}",
                        message="", from_email=None, recipient_list=recipient_list,
                        fail_silently=False, html_message=html_message
                    )
                    UpdateLog.objects.filter(id__in=selected_ids).update(is_sent=True)
                    TraceabilityLog.objects.create(user=request.user, action=f"Envió correo de novedades a {company.name}.")
                    messages.success(request, f"Correo para el ciclo finalizado ha sido enviado a {company.name}.")
                except Exception as e:
                    messages.error(request, f"Error al enviar el correo: {e}")
            else:
                messages.warning(request, f"La empresa {company.name} no tiene un correo configurado.")
            
            return redirect('review_and_send_novedades')

    # --- LÓGICA DE GET ---
    company_id = request.GET.get('company_id')
    selected_company = None
    novedades_pendientes = None

    relevant_updates = UpdateLog.objects.filter(
        is_sent=False,
        created_at__gte=start_of_cycle,
        # Usamos lte (menor o igual) para incluir las novedades guardadas justo al final
        created_at__lte=end_of_cycle 
    )
    
    company_ids_with_pending = relevant_updates.values_list('installation__company_id', flat=True).distinct()
    
    companies_with_pending_updates = Company.objects.filter(id__in=company_ids_with_pending).annotate(
        pending_count=Count('installations__updatelog', filter=Q(installations__updatelog__in=relevant_updates))
    ).filter(pending_count__gt=0).distinct()

    if company_id:
        selected_company = get_object_or_404(Company, id=company_id)
        
        # --- CORRECCIÓN DE ORDENAMIENTO (PARA LA VISTA) ---
        novedades_pendientes = relevant_updates.filter(
            installation__company=selected_company
        ).select_related(
            'operator_shift__operator', 'installation'
        ).annotate(
            effective_time=Coalesce('manual_timestamp', 'created_at__time', output_field=TimeField())
        ).order_by('installation__name', 'created_at__date', 'effective_time')

    context = {
        'companies': companies_with_pending_updates,
        'selected_company': selected_company,
        'novedades_pendientes': novedades_pendientes,
        'cycle_end': end_of_cycle,
        'cycle_start': start_of_cycle,
        'add_novedad_form': add_novedad_form,
    }
    return render(request, 'review_and_send.html', context)

@login_required
def ajax_get_installations_for_company(request, company_id):
    """
    Devuelve una lista de instalaciones para una empresa específica en formato JSON.
    Se usa para los dropdowns dinámicos.
    """
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

# Reemplaza tu función get_active_shift existente con esta versión corregida

def get_active_shift(user):
    """
    Función robusta para obtener el turno activo de un operador,
    manejando correctamente los turnos nocturnos que cruzan la medianoche.
    """
    now = timezone.now()
    today = now.date()
    yesterday = today - timedelta(days=1)

    # --- CAMBIO: Se reordena y mejora la lógica de prioridades ---

    # PRIORIDAD 1: Buscar un turno YA INICIADO en las últimas 18 horas.
    # EXPLICACIÓN: Esto captura de forma fiable cualquier turno en curso, incluyendo
    # los nocturnos que empezaron el día anterior.
    time_threshold = now - timedelta(hours=18)
    active_shift = OperatorShift.objects.select_related('shift_type', 'operator').filter(
        operator=user,
        actual_start_time__gte=time_threshold,
        actual_end_time__isnull=True
    ).order_by('-actual_start_time').first()

    if active_shift:
        return active_shift

    # PRIORIDAD 2: Si no hay un turno en curso, buscar un turno PENDIENTE
    # asignado para HOY O AYER.
    # EXPLICACIÓN: Esta es la corrección clave. Permite encontrar turnos
    # de noche (ej. 00:30) que fueron asignados al día anterior pero que
    # deben empezar en la madrugada de hoy.
    pending_shift = OperatorShift.objects.select_related('shift_type', 'operator').filter(
        operator=user,
        date__in=[today, yesterday],  # <-- CAMBIO: Busca en ambos días
        actual_start_time__isnull=True,
        actual_end_time__isnull=True
    ).order_by('-date', 'shift_type__start_time').first() # Ordena para priorizar el más reciente

    return pending_shift

@login_required
def start_shift(request):
    """
    Vista corregida que maneja la ACCIÓN de iniciar un turno.
    """
    if request.method == 'POST':
        # Busca el turno asignado más próximo que aún no ha comenzado
        shift_to_start = OperatorShift.objects.select_related('shift_type').filter(
            operator=request.user,
            actual_start_time__isnull=True,
            actual_end_time__isnull=True
        ).order_by('date', 'shift_type__start_time').first()

        if shift_to_start:
            shift_to_start.actual_start_time = timezone.now()
            shift_to_start.save()
            
            # Registro de trazabilidad
            TraceabilityLog.objects.create(
                user=request.user, 
                action="Inició turno."
            )
            
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
    active_notes = ShiftNote.objects.filter(is_active=True)
    
    # Formulario para crear notas de turno desde el modal
    shift_note_form = ShiftNoteForm()
    
    # Preparamos un contexto base
    context = {
        'active_shift': active_shift,
        'active_notes': active_notes,
        'shift_note_form': shift_note_form,
        }
    

    # Si el turno ya ha sido iniciado, calculamos todo el progreso y las tareas.
    if active_shift and active_shift.actual_start_time:
        progress_tasks = {}
        completed_tasks_count = 0
        total_tasks = 2 
        
        # 1. Lógica de Progreso
        total_rondas_requeridas = 7
        rondas_completadas = VirtualRoundLog.objects.filter(operator_shift=active_shift).count()
        progress_tasks['rondas'] = {'completed': (rondas_completadas >= total_rondas_requeridas), 'text': f"Rondas ({rondas_completadas}/{total_rondas_requeridas})"}
        if progress_tasks['rondas']['completed']: completed_tasks_count += 1

        empresas_con_instalaciones = Company.objects.filter(installations__isnull=False).distinct()
        ids_empresas_con_log = UpdateLog.objects.filter(operator_shift=active_shift).values_list('installation__company_id', flat=True).distinct()
        progress_tasks['bitacora'] = {'completed': (len(ids_empresas_con_log) >= empresas_con_instalaciones.count()), 'text': f"Bitácora ({len(ids_empresas_con_log)}/{empresas_con_instalaciones.count()})"}
        if progress_tasks['bitacora']['completed']: completed_tasks_count += 1
        
        
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


    # --- 👇 INICIO DEL NUEVO BLOQUE 👇 ---
        
        # --- 👇 INICIO DEL BLOQUE CORREGIDO 👇 ---
        
        # Lógica para el nuevo temporizador de rondas con reinicio a los 30 minutos
        round_completed_this_cycle = False
        last_round = VirtualRoundLog.objects.filter(operator_shift=active_shift).order_by('-start_time').first()
        
        if last_round:
            now = timezone.now()
            
            # Determinar el inicio del ciclo actual (ej: 16:30, 17:30)
            if now.minute >= 30:
                start_of_current_cycle = now.replace(minute=30, second=0, microsecond=0)
            else:
                start_of_current_cycle = (now - timedelta(hours=1)).replace(minute=30, second=0, microsecond=0)
            
            # Si la última ronda se inició dentro del ciclo actual, se marca como completada
            if last_round.start_time >= start_of_current_cycle:
                round_completed_this_cycle = True
        
        # Cambiamos el nombre de la variable para mayor claridad
        context['round_completed_this_cycle'] = round_completed_this_cycle
        context['shift_start_time_iso'] = active_shift.actual_start_time.isoformat()
        # --- 👆 FIN DEL BLOQUE CORREGIDO 👆 ---
    
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
def edit_update_log(request, log_id):
    # Obtenemos el log y nos aseguramos de que pertenezca al usuario actual para seguridad.
    log_entry = get_object_or_404(UpdateLog, id=log_id, operator_shift__operator=request.user)
    
    # Si la entrada ya fue editada, guardamos el mensaje original. Si no, lo hacemos ahora.
    if not log_entry.is_edited:
        log_entry.original_message = log_entry.message

    if request.method == 'POST':
        form = UpdateLogEditForm(request.POST, instance=log_entry)
        if form.is_valid():
            log_entry.is_edited = True
            log_entry.edited_at = timezone.now()
            form.save()
            
            # Registro de trazabilidad
            TraceabilityLog.objects.create(
                user=request.user, 
                action=f"Editó una entrada de la bitácora para la instalación '{log_entry.installation.name}'."
            )
            
            messages.success(request, 'La novedad ha sido actualizada correctamente.')
            return redirect('my_logbook')
    else:
        form = UpdateLogEditForm(instance=log_entry)

    context = {
        'form': form,
        'log_entry': log_entry
    }
    return render(request, 'edit_update_log.html', context)

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
            return redirect('update_log')
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

    # --- Lógica para la petición GET - Agrupando por fases ---
    checklist_items = get_applicable_checklist_items(active_shift)
    completed_logs_dict = {log.item.id: log for log in ChecklistLog.objects.filter(operator_shift=active_shift)}

    # Agrupar tareas por fase
    tasks_by_phase = {
        'start': [],
        'during': [],
        'end': []
    }

    for item in checklist_items:
        task_data = {
            'id': item.id,
            'description': item.description,
            'phase': item.phase,
            'completed': bool(completed_logs_dict.get(item.id)),
            'observation': completed_logs_dict.get(item.id).observacion if completed_logs_dict.get(item.id) else ''
        }
        tasks_by_phase[item.phase].append(task_data)

    # Lista completa para compatibilidad con JavaScript existente
    tasks_for_js = []
    for phase_tasks in tasks_by_phase.values():
        tasks_for_js.extend(phase_tasks)

    context = {
        'checklist_items': checklist_items,
        'completed_logs_dict': completed_logs_dict,
        'tasks_for_js': tasks_for_js,
        'tasks_by_phase': tasks_by_phase,
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

    # --- Lógica de validación (sin cambios) ---
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
    
    if validation_errors:
        full_error_message = "No puedes finalizar el turno. Tareas pendientes: " + " ".join(validation_errors)
        messages.error(request, full_error_message)
        return redirect('operator_dashboard')

    end_time = timezone.now()
    duration_timedelta = end_time - active_shift.actual_start_time
    total_seconds = int(duration_timedelta.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    formatted_duration = f"{hours}h {minutes}m"

    # --- INICIO DE LA LÓGICA DE ORDENACIÓN DEL CHECKLIST ---
    
    # 1. Obtenemos todos los logs del checklist para el turno.
    completed_checklist_qs = ChecklistLog.objects.filter(
        operator_shift=active_shift
    ).select_related('item').order_by('completed_at')

    # 2. Definimos el orden correcto de las fases.
    phase_order = ['start', 'during', 'end']
    phase_display_names = {
        'start': '🚀 INICIO DE TURNO',
        'during': '⏰ DURANTE EL TURNO',
        'end': '🏁 FINALIZACIÓN DE TURNO'
    }

    # 3. Creamos un diccionario ordenado para mantener la secuencia.
    checklist_by_phase = OrderedDict()
    for phase_key in phase_order:
        # Filtramos los logs que corresponden a la fase actual del bucle
        logs_for_phase = completed_checklist_qs.filter(item__phase=phase_key)
        # Si hay logs para esta fase, los añadimos al diccionario
        if logs_for_phase.exists():
            checklist_by_phase[phase_key] = {
                'display_name': phase_display_names.get(phase_key),
                'logs': logs_for_phase
            }
    # --- FIN DE LA LÓGICA DE ORDENACIÓN ---

    updates_log = UpdateLog.objects.filter(
        operator_shift=active_shift
    ).select_related('installation__company').order_by('installation__company__name', 'installation__name', 'created_at')
    
    rondas_virtuales = VirtualRoundLog.objects.filter(operator_shift=active_shift)

    context = {
        'operator': request.user,
        'start_time': active_shift.actual_start_time,
        'end_time': end_time,
        'duration': formatted_duration,
        'current_time': timezone.now(),
        'checklist_by_phase': checklist_by_phase, # Pasamos el nuevo diccionario ordenado
        'updates_log': updates_log,
        'rondas_virtuales': rondas_virtuales,
    }

    # El resto de la lógica para generar el PDF se mantiene igual
    template = get_template('turn_report_pdf.html')
    html = template.render(context)
    result = BytesIO()
     # --- 👇 MODIFICA ESTA SECCIÓN 👇 ---
    pdf = pisa.pisaDocument(
        BytesIO(html.encode("UTF-8")),
        result,
        link_callback=link_callback  # <-- AÑADE ESTE ARGUMENTO
    )
    # --- 👆 FIN DE LA MODIFICACIÓN 👆 ---

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
            
            # --- 👇 INICIO DE LA CORRECCIÓN 👇 ---
            # 1. Obtenemos el total de segundos como un número entero.
            total_seconds = int(duration.total_seconds())
            
            # 2. Usamos divmod para obtener los minutos y segundos restantes.
            minutes, seconds = divmod(total_seconds, 60)
            
            # 3. Creamos el texto formateado.
            formatted_duration = f"{minutes} min {seconds} seg"
            
            # 4. Guardamos el registro de actividad con el nuevo formato.
            TraceabilityLog.objects.create(
                user=request.user, 
                action=f"Finalizó ronda virtual. Duración: {formatted_duration}."
            )
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

    if request.method == 'POST':
        # Directamente obtenemos el turno desde el reporte para evitar ambigüedades
        shift_to_close = report.operator_shift

        if shift_to_close:
            # 1. Marca el turno como finalizado
            shift_to_close.actual_end_time = timezone.now()
            shift_to_close.save()

            # 2. Marca el reporte como firmado
            report.is_signed = True
            report.signed_at = timezone.now()
            report.save()

            # 3. Crea el registro de trazabilidad
            TraceabilityLog.objects.create(user=request.user, action="Firmó y finalizó su reporte de turno.")

            # 4. Cierra la sesión del usuario
            user_was_logged_in = request.user.is_authenticated
            if user_was_logged_in:
                logout(request)

            # 5. Redirige a la página de login con un mensaje de éxito
            messages.success(request, "Turno finalizado con éxito. Por favor, inicie sesión nuevamente si es necesario.")
            return redirect('login')
        else:
            messages.error(request, "Error: No se pudo encontrar el turno asociado a este reporte.")
            return redirect('operator_dashboard')

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
    Lógica de alarmas corregida para ignorar tareas con tiempo de alarma en cero.
    """
    active_shift = get_active_shift(request.user)
    overdue_tasks = []

    if active_shift and active_shift.actual_start_time:
        now = timezone.now()
        
        applicable_items = get_applicable_checklist_items(active_shift)
        
        completed_item_ids = ChecklistLog.objects.filter(
            operator_shift=active_shift
        ).values_list('item_id', flat=True)
        
        # --- 👇 INICIO DE LA CORRECCIÓN CLAVE 👇 ---
        # Ahora, además de verificar que la alarma no sea nula,
        # nos aseguramos de que su duración sea mayor a cero segundos.
        pending_items_with_alarm = applicable_items.exclude(
            id__in=completed_item_ids
        ).filter(
            alarm_trigger_delay__isnull=False,
            alarm_trigger_delay__gt=timedelta(seconds=0) # <-- LÍNEA AÑADIDA
        )
        # --- 👆 FIN DE LA CORRECCIÓN 👆 ---
        
        for item in pending_items_with_alarm:
            due_time = active_shift.actual_start_time + item.alarm_trigger_delay
            if now > due_time:
                overdue_tasks.append({'description': item.description})

    return JsonResponse({'overdue_tasks': overdue_tasks})


# --- VISTAS DE CONTACTOS DE EMERGENCIA ---

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
    else:
        form = EmergencyContactForm()
    return render(request, 'emergency_contact_form.html', {'form': form, 'title': 'Añadir Contacto de Emergencia'})

@login_required
@user_passes_test(is_supervisor)
def edit_emergency_contact(request, contact_id):
    contact = get_object_or_404(EmergencyContact, id=contact_id)
    if request.method == 'POST':
        form = EmergencyContactForm(request.POST, instance=contact)
        if form.is_valid():
            form.save()
            messages.success(request, "Contacto de emergencia actualizado con éxito.")
            return redirect('manage_emergency_contacts')
    else:
        form = EmergencyContactForm(instance=contact)
    return render(request, 'emergency_contact_form.html', {'form': form, 'title': 'Editar Contacto de Emergencia'})

@login_required
@user_passes_test(is_supervisor)
def delete_emergency_contact(request, contact_id):
    contact = get_object_or_404(EmergencyContact, id=contact_id)
    if request.method == 'POST':
        contact.delete()
        messages.success(request, "Contacto de emergencia eliminado.")
        return redirect('manage_emergency_contacts')
    return render(request, 'emergency_contact_confirm_delete.html', {'contact': contact})

@login_required
def panic_button_view(request):
    # Agrupamos los contactos para una visualización clara
    contacts_by_company = defaultdict(lambda: defaultdict(list))
    general_contacts = []

    # Obtenemos todos los contactos y los pre-cargamos para eficiencia
    all_contacts = EmergencyContact.objects.select_related('company', 'installation').all()

    for contact in all_contacts:
        if not contact.company and not contact.installation:
            general_contacts.append(contact)
        elif contact.company and not contact.installation:
            contacts_by_company[contact.company.name]['company_contacts'].append(contact)
        elif contact.installation:
            company_name = contact.installation.company.name
            contacts_by_company[company_name][contact.installation.name].append(contact)

    context = {
        'general_contacts': general_contacts,
        'contacts_by_company': dict(contacts_by_company)
    }
    
    # Convertir defaultdicts anidados a dicts normales
    for company_name in context['contacts_by_company']:
        context['contacts_by_company'][company_name] = dict(context['contacts_by_company'][company_name])
    
    return render(request, 'panic_button.html', context)

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

@login_required
def full_logbook_view(request):
    """
    Muestra la bitácora del turno actual y los dos turnos anteriores.
    """
    shift_ids_to_show = []

    # 1. Encontrar el(los) turno(s) activo(s)
    active_shifts = OperatorShift.objects.filter(
        actual_start_time__isnull=False,
        actual_end_time__isnull=True
    ).order_by('actual_start_time')

    if active_shifts.exists():
        shift_ids_to_show.extend(list(active_shifts.values_list('id', flat=True)))

        # 2. Encontrar los 2 turnos completados antes del inicio del turno activo más antiguo
        earliest_active_start_time = active_shifts.first().actual_start_time
        previous_shifts = OperatorShift.objects.filter(
            actual_end_time__isnull=False,
            actual_end_time__lt=earliest_active_start_time
        ).order_by('-actual_end_time')[:2]
        shift_ids_to_show.extend(list(previous_shifts.values_list('id', flat=True)))
    else:
        # Plan B: Si no hay turnos activos, muestra los últimos 3 turnos completados
        previous_shifts = OperatorShift.objects.filter(
            actual_end_time__isnull=False
        ).order_by('-actual_end_time')[:3]
        shift_ids_to_show.extend(list(previous_shifts.values_list('id', flat=True)))

    # 3. Obtener y ordenar los logs de los turnos seleccionados
    logs = UpdateLog.objects.filter(
        operator_shift_id__in=shift_ids_to_show
    ).select_related(
        'operator_shift__shift_type', 'operator_shift__operator', 'installation__company'
    ).order_by('operator_shift__actual_start_time', 'created_at')

    # 4. Agrupar logs por turno, manteniendo el orden cronológico
    logs_by_shift = OrderedDict()
    for log in logs:
        shift = log.operator_shift
        if shift not in logs_by_shift:
            logs_by_shift[shift] = []
        logs_by_shift[shift].append(log)

    context = {
        'logs_by_shift': logs_by_shift,
    }
    return render(request, 'full_logbook.html', context)

@login_required
def dismiss_shift_note(request, note_id):
    """
    Marca una nota de turno como inactiva (leída/descartada).
    """
    if request.method == 'POST':
        note = get_object_or_404(ShiftNote, id=note_id)
        note.is_active = False
        note.save()
        messages.info(request, "Nota marcada como leída.")
    return redirect('operator_dashboard')

@login_required
def create_shift_note_modal(request):
    """
    Vista para crear una nota de turno desde el modal en el dashboard.
    """
    if request.method == 'POST':
        form = ShiftNoteForm(request.POST)
        if form.is_valid():
            note = form.save(commit=False)
            note.created_by = request.user
            note.save()
            messages.success(request, "Nota para el próximo turno guardada con éxito.")
            return redirect('operator_dashboard')
        else:
            messages.error(request, "Error al guardar la nota. Por favor, revisa los datos.")
    return redirect('operator_dashboard')

@login_required
@user_passes_test(is_supervisor)
def current_logbook_view(request):
    """
    Muestra al supervisor la bitácora actual del operador en turno.
    """
    # Buscar operadores con turnos activos
    active_shifts = OperatorShift.objects.filter(
        actual_start_time__isnull=False,
        actual_end_time__isnull=True
    ).select_related('operator', 'shift_type')
    
    current_logbook_data = {}
    
    for shift in active_shifts:
        operator_name = f"{shift.operator.first_name} {shift.operator.last_name}"
        
        # Obtener las novedades del turno actual
        logs_del_turno = UpdateLog.objects.filter(
            operator_shift=shift
        ).select_related('installation', 'installation__company').order_by('-created_at')
        
        if logs_del_turno.exists():
            logbook_data = {}
            for log in logs_del_turno:
                if log.installation and log.installation.company:
                    company_name = log.installation.company.name
                    installation_name = log.installation.name
                    
                    if company_name not in logbook_data:
                        logbook_data[company_name] = {}
                    
                    if installation_name not in logbook_data[company_name]:
                        logbook_data[company_name][installation_name] = []
                    
                    logbook_data[company_name][installation_name].append(log)
            
            current_logbook_data[operator_name] = {
                'shift': shift,
                'logbook_data': logbook_data
            }
    
    context = {
        'current_logbook_data': current_logbook_data
    }
    
    return render(request, 'current_logbook.html', context)

def delete_update_log(request, log_id):
    # Asegura que el log pertenezca al usuario actual antes de intentar obtenerlo
    log_entry = get_object_or_404(UpdateLog, id=log_id, operator_shift__operator=request.user)
    
    if request.method == 'POST':
        try:
            # 1. Elimina la entrada
            log_entry.delete()
            
            # 2. Registra la acción en el historial
            TraceabilityLog.objects.create(
                user=request.user,
                action=f"Eliminó una entrada de la bitácora para la instalación '{log_entry.installation.name}'."
            )
            
            # 3. Devuelve una respuesta JSON para la petición AJAX (CORRECCIÓN)
            return JsonResponse({
                'status': 'success', 
                'message': 'La novedad ha sido eliminada correctamente.'
            })
            
        except Exception as e:
            # Manejo de errores en caso de fallo en el proceso
            return JsonResponse({
                'status': 'error', 
                'message': f'Error al eliminar la novedad: {e}'
            }, status=400) # Devolver un código de estado de error HTTP
            
    # Si la petición no es POST, muestra la página de confirmación (comportamiento original)
    return render(request, 'delete_update_log_confirm.html', {'log_entry': log_entry})

# Vistas para Seguridad Vehicular
@login_required
@user_passes_test(is_supervisor)
def vehicle_security_dashboard(request):
    """Vista principal del dashboard de seguridad vehicular"""
    import requests
    from datetime import datetime, timedelta
    
    CIUDADES_CHILE = {
        'punta arenas': {'lat': -53.162, 'lon': -70.917},
        'puerto natales': {'lat': -51.723, 'lon': -72.497},
        'santiago': {'lat': -33.45, 'lon': -70.66},
        'valparaiso': {'lat': -33.045, 'lon': -71.619},
        'concepcion': {'lat': -36.826, 'lon': -73.050},
    }
    # Obtener datos de vehículos
    ciudad_buscada = request.GET.get('ciudad', 'punta arenas').lower()
    coordenadas = CIUDADES_CHILE.get(ciudad_buscada, CIUDADES_CHILE['punta arenas'])
    
    vehicles = Vehicle.objects.filter(is_active=True)
    
    # Estadísticas generales
    total_vehicles = vehicles.count()
    vehicles_on_route = 0
    vehicles_stopped = 0
    vehicles_disconnected = 0
    
    # Obtener posiciones más recientes de cada vehículo
    vehicle_positions = []
    for vehicle in vehicles:
        latest_position = VehiclePosition.objects.filter(vehicle=vehicle).order_by('-timestamp').first()
        if latest_position:
            vehicle_positions.append({
                'vehicle': vehicle.license_plate,
                'lat': float(latest_position.latitude),
                'lng': float(latest_position.longitude),
                'speed': latest_position.speed,
                'connected': latest_position.is_connected,
                'driver': vehicle.driver_name
            })
    
    # Contar estados de vehículos
    for pos in vehicle_positions:
        if not pos['connected']:
            vehicles_disconnected += 1
        elif pos['speed'] > 5:
            vehicles_on_route += 1
        else:
            vehicles_stopped += 1
    
    # Obtener alertas activas desde la base de datos
    active_alerts = VehicleAlert.objects.filter(
        is_resolved=False,
        vehicle__is_active=True
    ).select_related('vehicle').order_by('-created_at')[:10]
    
    vehicle_alerts = []
    for alert in active_alerts:
        vehicle_alerts.append({
            'vehicle': alert.vehicle.license_plate,
            'type': alert.alert_type,
            'message': alert.message,
            'time': alert.created_at.strftime('%H:%M')
        })
    
    # Obtener rutas recientes para reportes
    recent_routes = VehicleRoute.objects.filter(
        vehicle__is_active=True,
        start_time__date=timezone.now().date()
    ).select_related('vehicle').order_by('-start_time')[:10]
    
    vehicle_reports = []
    for route in recent_routes:
        status = 'Ruta completada' if route.end_time else 'En progreso'
        time_info = f'{route.total_distance:.1f} km' if route.total_distance else 'N/A'
        vehicle_reports.append({
            'vehicle': route.vehicle.license_plate,
            'driver': route.vehicle.driver_name,
            'time': time_info,
            'issue': status
        })
    
    # Obtener clima para Punta Arenas, Chile
    try:
        # API Key de OpenWeatherMap (deberías configurar esto en settings.py)
        api_key = "tu_api_key_aqui"  # Reemplazar con tu API key real
        city = "Punta Arenas"
        country = "CL"
        
        weather_url = f"http://api.openweathermap.org/data/2.5/weather?q={city},{country}&appid={api_key}&units=metric&lang=es"
        response = requests.get(weather_url, timeout=5)
        
        if response.status_code == 200:
            weather_json = response.json()
            weather_data = {
                'temperature': round(weather_json['main']['temp']),
                'description': weather_json['weather'][0]['description'].capitalize(),
                'humidity': weather_json['main']['humidity'],
                'wind_speed': round(weather_json['wind']['speed'] * 3.6)  # Convertir m/s a km/h
            }
        else:
            # Datos de respaldo para Punta Arenas
            weather_data = {
                'temperature': 8,
                'description': 'Viento fuerte',
                'humidity': 75,
                'wind_speed': 35
            }
    except Exception as e:
        # Datos de respaldo en caso de error
        weather_data = {
            'temperature': 8,
            'description': 'Viento fuerte',
            'humidity': 75,
            'wind_speed': 35
        }
    
    # Estadísticas adicionales
    stats = {
        'speed_violations': 3,
        'stopped_time_avg': 45,  # minutos
        'longest_drive_time': 8,  # horas
        'connection_issues': 2
    }
    
    # Preparar datos de vehículos para JavaScript
    vehicles_data = []
    for vehicle in vehicles:
        latest_position = VehiclePosition.objects.filter(vehicle=vehicle).order_by('-timestamp').first()
        if latest_position:
            vehicles_data.append({
                'id': vehicle.id,
                'name': vehicle.license_plate,
                'lat': float(latest_position.latitude),
                'lng': float(latest_position.longitude),
                'speed': latest_position.speed,
                'status': 'En ruta' if latest_position.speed > 5 else ('Offline' if not latest_position.is_connected else 'Detenido'),
                'driver': vehicle.driver_name,
                'weather': {
                    'temp': 8,  # Datos climáticos por defecto - se pueden integrar con API externa
                    'condition': 'Viento fuerte',
                    'icon': '💨'
                },
                'speedLimit': 50,  # Límite por defecto
                'fuel': 75,  # Datos por defecto - se pueden agregar campos al modelo
                'odometer': 45230,
                'lastMaintenance': '15/11/2024',
                'model': f'{vehicle.get_vehicle_type_display()} {vehicle.created_at.year}',
                'engine': 'Encendido' if latest_position.speed > 0 else 'Apagado',
                'doors': 'Cerradas',
                'battery': 95
            })
    
    # Si no hay vehículos con posiciones, usar lista vacía
    if not vehicles_data:
        vehicles_data = []
    
    context = {
        'waze_lat': coordenadas['lat'],
        'waze_lon': coordenadas['lon'],
        'ciudad_actual': ciudad_buscada.title(),
        'vehicles': vehicles,
        'vehicles_data': json.dumps(vehicles_data),  # Datos serializados para JavaScript
        'vehicle_positions': vehicle_positions,
        'vehicle_alerts': vehicle_alerts,
        'vehicle_reports': vehicle_reports,
        'weather_data': weather_data,
        'stats': stats,
        'total_vehicles': len(vehicle_positions),
        'vehicles_on_route': vehicles_on_route,
        'vehicles_stopped': vehicles_stopped,
        'vehicles_disconnected': vehicles_disconnected,
    }
    
    return render(request, 'vehicle_security_dashboard.html', context)

@login_required
@user_passes_test(is_supervisor)
def vehicle_activity_log(request):
    """Vista del registro de actividades de vehículos"""
    
    # Datos de prueba para el registro de actividades
    demo_activities = [
        {
            'id': 1,
            'vehicle': 'ABC-123',
            'driver': 'Juan Pérez',
            'start_time': '08:00',
            'end_time': '16:30',
            'route': 'Santiago - Valparaíso',
            'distance': '120 km',
            'avg_speed': '65 km/h',
            'max_speed': '85 km/h',
            'stop_time': '45 min',
            'weather': 'Soleado'
        },
        {
            'id': 2,
            'vehicle': 'DEF-456',
            'driver': 'María González',
            'start_time': '09:15',
            'end_time': '17:45',
            'route': 'Santiago - Rancagua',
            'distance': '87 km',
            'avg_speed': '58 km/h',
            'max_speed': '75 km/h',
            'stop_time': '120 min',
            'weather': 'Nublado'
        },
        {
            'id': 3,
            'vehicle': 'GHI-789',
            'driver': 'Carlos López',
            'start_time': '07:30',
            'end_time': '15:00',
            'route': 'Santiago - Melipilla',
            'distance': '65 km',
            'avg_speed': '72 km/h',
            'max_speed': '90 km/h',
            'stop_time': '30 min',
            'weather': 'Lluvia ligera'
        }
    ]
    
    context = {
        'activities': demo_activities
    }
    
    return render(request, 'vehicle_activity_log.html', context)

@login_required
@user_passes_test(is_supervisor)
def vehicle_route_detail(request, activity_id):
    """Vista del detalle de una ruta específica"""
    
    # Datos de prueba para el detalle de ruta
    demo_route_details = {
        1: {
            'vehicle': 'ABC-123',
            'driver': 'Juan Pérez',
            'start_time': '08:00',
            'end_time': '16:30',
            'duration': '8h 30min',
            'route': 'Santiago - Valparaíso',
            'distance': '120 km',
            'avg_speed': '65 km/h',
            'max_speed': '85 km/h',
            'stop_time': '45 min',
            'weather_start': 'Soleado, 18°C',
            'weather_end': 'Parcialmente nublado, 22°C',
            'route_points': [
                {'lat': -33.4489, 'lng': -70.6693, 'time': '08:00', 'speed': 0},
                {'lat': -33.4200, 'lng': -70.7000, 'time': '08:30', 'speed': 60},
                {'lat': -33.3500, 'lng': -70.8000, 'time': '09:15', 'speed': 70},
                {'lat': -33.0472, 'lng': -71.6127, 'time': '10:30', 'speed': 0},  # Valparaíso
            ],
            'stops': [
                {'location': 'Estación de Servicio Quilpué', 'duration': '15 min', 'time': '10:15'},
                {'location': 'Centro de Distribución Valparaíso', 'duration': '30 min', 'time': '11:00'},
            ],
            'alerts': [
                {'type': 'speed', 'message': 'Exceso de velocidad: 85 km/h', 'time': '09:45', 'location': 'Ruta 68 km 45'},
            ]
        },
        2: {
            'vehicle': 'DEF-456',
            'driver': 'María González',
            'start_time': '09:15',
            'end_time': '17:45',
            'duration': '8h 30min',
            'route': 'Santiago - Rancagua',
            'distance': '87 km',
            'avg_speed': '58 km/h',
            'max_speed': '75 km/h',
            'stop_time': '120 min',
            'weather_start': 'Nublado, 16°C',
            'weather_end': 'Nublado, 19°C',
            'route_points': [
                {'lat': -33.4489, 'lng': -70.6693, 'time': '09:15', 'speed': 0},
                {'lat': -33.5000, 'lng': -70.7000, 'time': '09:45', 'speed': 55},
                {'lat': -34.1694, 'lng': -70.7407, 'time': '11:00', 'speed': 0},  # Rancagua
            ],
            'stops': [
                {'location': 'Centro Logístico Rancagua', 'duration': '90 min', 'time': '11:30'},
                {'location': 'Almuerzo', 'duration': '30 min', 'time': '13:00'},
            ],
            'alerts': []
        },
        3: {
            'vehicle': 'GHI-789',
            'driver': 'Carlos López',
            'start_time': '07:30',
            'end_time': '15:00',
            'duration': '7h 30min',
            'route': 'Santiago - Melipilla',
            'distance': '65 km',
            'avg_speed': '72 km/h',
            'max_speed': '90 km/h',
            'stop_time': '30 min',
            'weather_start': 'Lluvia ligera, 14°C',
            'weather_end': 'Lluvia ligera, 16°C',
            'route_points': [
                {'lat': -33.4489, 'lng': -70.6693, 'time': '07:30', 'speed': 0},
                {'lat': -33.5000, 'lng': -70.8000, 'time': '08:00', 'speed': 65},
                {'lat': -33.6881, 'lng': -71.2156, 'time': '08:45', 'speed': 0},  # Melipilla
            ],
            'stops': [
                {'location': 'Planta Melipilla', 'duration': '30 min', 'time': '09:00'},
            ],
            'alerts': [
                {'type': 'speed', 'message': 'Exceso de velocidad: 90 km/h en lluvia', 'time': '08:15', 'location': 'Ruta 78 km 25'},
                {'type': 'weather', 'message': 'Conducción en condiciones de lluvia', 'time': '07:30', 'location': 'Todo el trayecto'},
            ]
        }
    }
    
    route_detail = demo_route_details.get(activity_id, demo_route_details[1])
    
    context = {
        'route_detail': route_detail,
        'activity_id': activity_id
    }
    
    return render(request, 'vehicle_route_detail.html', context)

@login_required
@user_passes_test(is_supervisor)
def get_weather_data(request):
    """API para obtener datos del clima usando OpenWeatherMap"""
    import requests
    
    lat = request.GET.get('lat', -33.4489)  # Santiago por defecto
    lon = request.GET.get('lon', -70.6693)
    
    api_key = 'af043322c5d5657c7b6c16a888ecd196'
    url = f'https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units=metric&lang=es'
    
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            weather_data = {
                'temperature': round(data['main']['temp']),
                'description': data['weather'][0]['description'].title(),
                'humidity': data['main']['humidity'],
                'wind_speed': round(data['wind']['speed'] * 3.6),  # Convertir m/s a km/h
                'icon': data['weather'][0]['icon']
            }
            return JsonResponse(weather_data)
        else:
            # Datos de respaldo si la API falla
            return JsonResponse({
                'temperature': 20,
                'description': 'Datos no disponibles',
                'humidity': 60,
                'wind_speed': 10,
                'icon': '01d'
            })
    except Exception as e:
        # Datos de respaldo en caso de error
        return JsonResponse({
            'temperature': 20,
            'description': 'Error al obtener datos',
            'humidity': 60,
            'wind_speed': 10,
            'icon': '01d'
        })

@login_required
def check_first_round_started(request):
    """
    Verifica si ya se ha iniciado alguna ronda en el turno activo.
    Usado por el JavaScript del contador de rondas.
    """
    active_shift = get_active_shift(request.user)
    
    if active_shift:
        has_rounds = VirtualRoundLog.objects.filter(
            operator_shift=active_shift
        ).exists()
        
        return JsonResponse({'has_rounds': has_rounds})
    
    return JsonResponse({'has_rounds': False})


@login_required
@user_passes_test(is_supervisor)
def get_multiple_cities_weather(request):
    """API para obtener datos del clima de múltiples ciudades"""
    import requests
    
    # Ciudades predefinidas con sus coordenadas - Cobertura completa de Chile
    cities = {
        'arica': {'name': 'Arica', 'lat': -18.4783, 'lon': -70.3126, 'country': 'CL'},
        'iquique': {'name': 'Iquique', 'lat': -20.2307, 'lon': -70.1355, 'country': 'CL'},
        'antofagasta': {'name': 'Antofagasta', 'lat': -23.6509, 'lon': -70.3975, 'country': 'CL'},
        'calama': {'name': 'Calama', 'lat': -22.4667, 'lon': -68.9333, 'country': 'CL'},
        'copiapo': {'name': 'Copiapó', 'lat': -27.3668, 'lon': -70.3323, 'country': 'CL'},
        'la_serena': {'name': 'La Serena', 'lat': -29.9027, 'lon': -71.2519, 'country': 'CL'},
        'coquimbo': {'name': 'Coquimbo', 'lat': -29.9533, 'lon': -71.3436, 'country': 'CL'},
        'valparaiso': {'name': 'Valparaíso', 'lat': -33.0458, 'lon': -71.6197, 'country': 'CL'},
        'vina_del_mar': {'name': 'Viña del Mar', 'lat': -33.0153, 'lon': -71.5500, 'country': 'CL'},
        'santiago': {'name': 'Santiago', 'lat': -33.4489, 'lon': -70.6693, 'country': 'CL'},
        'rancagua': {'name': 'Rancagua', 'lat': -34.1708, 'lon': -70.7394, 'country': 'CL'},
        'talca': {'name': 'Talca', 'lat': -35.4264, 'lon': -71.6554, 'country': 'CL'},
        'curico': {'name': 'Curicó', 'lat': -34.9833, 'lon': -71.2394, 'country': 'CL'},
        'chillan': {'name': 'Chillán', 'lat': -36.6061, 'lon': -72.1039, 'country': 'CL'},
        'concepcion': {'name': 'Concepción', 'lat': -36.8201, 'lon': -73.0444, 'country': 'CL'},
        'talcahuano': {'name': 'Talcahuano', 'lat': -36.7167, 'lon': -73.1167, 'country': 'CL'},
        'los_angeles': {'name': 'Los Ángeles', 'lat': -37.4689, 'lon': -72.3539, 'country': 'CL'},
        'temuco': {'name': 'Temuco', 'lat': -38.7359, 'lon': -72.5904, 'country': 'CL'},
        'valdivia': {'name': 'Valdivia', 'lat': -39.8142, 'lon': -73.2459, 'country': 'CL'},
        'osorno': {'name': 'Osorno', 'lat': -40.5742, 'lon': -73.1317, 'country': 'CL'},
        'puerto_montt': {'name': 'Puerto Montt', 'lat': -41.4693, 'lon': -72.9424, 'country': 'CL'},
        'castro': {'name': 'Castro', 'lat': -42.4833, 'lon': -73.7667, 'country': 'CL'},
        'coyhaique': {'name': 'Coyhaique', 'lat': -45.5752, 'lon': -72.0662, 'country': 'CL'},
        'punta_arenas': {'name': 'Punta Arenas', 'lat': -53.1638, 'lon': -70.9171, 'country': 'CL'},
        'puerto_natales': {'name': 'Puerto Natales', 'lat': -51.7236, 'lon': -72.5064, 'country': 'CL'}
    }
    
    # Obtener ciudades solicitadas (por defecto todas)
    requested_cities = request.GET.get('cities', 'santiago,punta_arenas,valparaiso').split(',')
    
    api_key = 'af043322c5d5657c7b6c16a888ecd196'
    weather_results = {}
    
    for city_key in requested_cities:
        if city_key in cities:
            city_info = cities[city_key]
            url = f'https://api.openweathermap.org/data/2.5/weather?lat={city_info["lat"]}&lon={city_info["lon"]}&appid={api_key}&units=metric&lang=es'
            
            try:
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    weather_results[city_key] = {
                        'name': city_info['name'],
                        'temperature': round(data['main']['temp']),
                        'description': data['weather'][0]['description'].title(),
                        'humidity': data['main']['humidity'],
                        'wind_speed': round(data['wind']['speed'] * 3.6),
                        'icon': data['weather'][0]['icon'],
                        'lat': city_info['lat'],
                        'lon': city_info['lon']
                    }
                else:
                    # Datos de respaldo si la API falla
                    weather_results[city_key] = {
                        'name': city_info['name'],
                        'temperature': 15,
                        'description': 'Datos no disponibles',
                        'humidity': 60,
                        'wind_speed': 15,
                        'icon': '01d',
                        'lat': city_info['lat'],
                        'lon': city_info['lon']
                    }
            except Exception as e:
                # Datos de respaldo en caso de error
                weather_results[city_key] = {
                    'name': city_info['name'],
                    'temperature': 15,
                    'description': 'Error al obtener datos',
                    'humidity': 60,
                    'wind_speed': 15,
                    'icon': '01d',
                    'lat': city_info['lat'],
                    'lon': city_info['lon']
                }
    
    return JsonResponse(weather_results)