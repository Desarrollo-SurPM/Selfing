from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.template.loader import get_template
from xhtml2pdf import pisa
from django.contrib import messages 
from io import BytesIO
from django.core.files.base import ContentFile
from django import forms
from datetime import timedelta

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

@login_required
def home(request):
    if is_supervisor(request.user):
        return redirect('admin_dashboard')
    
    # Lógica para registrar el inicio del turno del operador
    today = timezone.now().date()
    # Busca un turno asignado para hoy que aún no haya comenzado oficialmente
    active_shift = OperatorShift.objects.filter(operator=request.user, date=today, actual_start_time__isnull=True).first()
    
    if active_shift:
        active_shift.actual_start_time = timezone.now()
        active_shift.save()
        TraceabilityLog.objects.create(user=request.user, action="Inició turno.")
        
    return redirect('operator_dashboard')

# --- VISTAS DE ADMINISTRADOR ---

@login_required
@user_passes_test(is_supervisor)
def admin_dashboard(request):
    today = timezone.now().date()
    novedades_hoy = UpdateLog.objects.filter(created_at__date=today).count()
    correos_pendientes_count = Email.objects.filter(status='pending').count()
    operadores_activos = User.objects.filter(is_superuser=False, is_active=True).count()
    servicios_monitoreados_activos = MonitoredService.objects.filter(is_active=True).count()
    traceability_logs = TraceabilityLog.objects.all().order_by('-timestamp')[:6]
    reports = UpdateLog.objects.filter(created_at__date=today).order_by('-created_at')
    pending_emails = Email.objects.filter(status='pending').order_by('-created_at')
    monitored_services = MonitoredService.objects.filter(is_active=True)
    status_list = []
    for service in monitored_services:
        latest_log = service.logs.order_by('-timestamp').first()
        status_list.append({
            'id': service.id,
            'name': service.name,
            'status': latest_log.is_up if latest_log else None,
        })
    context = {
        'novedades_hoy': novedades_hoy,
        'correos_pendientes_count': correos_pendientes_count,
        'operadores_activos': operadores_activos,
        'servicios_monitoreados_activos': servicios_monitoreados_activos,
        'reports': reports,
        'pending_emails': pending_emails,
        'traceability_logs': traceability_logs,
        'service_status_list': status_list
    }
    return render(request, 'admin_dashboard.html', context)

# --- (Vistas CRUD para Operadores, Empresas, Instalaciones, Checklist, Monitoreo, etc.) ---
# (Estas vistas no cambian funcionalmente, solo se lista el código para asegurar que esté completo)

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
    return render(request, 'manage_companies.html', {'companies': companies})

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
    reports = TurnReport.objects.filter(is_signed=True).order_by('-end_time')
    return render(request, 'view_turn_reports.html', {'reports': reports})

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
# --- VISTAS DE OPERADOR ---

def get_active_shift(user):
    """Función auxiliar para obtener el turno activo de un operador."""
    return OperatorShift.objects.filter(operator=user, date=timezone.now().date()).first()

@login_required
def operator_dashboard(request):
    monitored_services = MonitoredService.objects.filter(is_active=True)
    status_list = []
    for service in monitored_services:
        latest_log = service.logs.order_by('-timestamp').first()
        status_list.append({ 'id': service.id, 'name': service.name, 'status': latest_log.is_up if latest_log else None })
    
    context = {
        'service_status_list': status_list,
        'active_round_id': request.session.get('active_round_id')
    }
    return render(request, 'operator_dashboard.html', context)

@login_required
def checklist_view(request):
    active_shift = get_active_shift(request.user)
    if not active_shift:
        return redirect('operator_dashboard')

    if request.method == 'POST':
        item_ids = request.POST.getlist('items')
        for item_id in item_ids:
            item = get_object_or_404(ChecklistItem, id=item_id)
            # Usamos get_or_create para evitar duplicados si se envía el formulario varias veces
            ChecklistLog.objects.get_or_create(operator_shift=active_shift, item=item)
            TraceabilityLog.objects.create(user=request.user, action=f"Completó checklist: {item.description}")
        return redirect('checklist')

    # --- LÓGICA DE AGRUPACIÓN DE TAREAS ---
    
    # Obtenemos las tareas ya completadas en este turno
    completed_in_shift_ids = list(ChecklistLog.objects.filter(operator_shift=active_shift).values_list('item_id', flat=True))
    
    # Agrupamos todas las tareas del checklist por su fase
    checklist_items_by_phase = {}
    for phase_code, phase_name in ChecklistItem.TurnPhase.choices:
        items = ChecklistItem.objects.filter(phase=phase_code)
        if items.exists():
            checklist_items_by_phase[phase_name] = items

    context = {
        'checklist_data': checklist_items_by_phase,
        'completed_ids': completed_in_shift_ids
    }
    return render(request, 'checklist.html', context)


@login_required
def update_log_view(request):
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
    if not active_shift:
        return redirect('operator_dashboard')

    # --- INICIO DE LA LÓGICA DE VALIDACIÓN ---
    # 1. Encontrar todas las empresas que tuvieron novedades en este turno
    companies_with_updates = Company.objects.filter(
        installations__updatelog__operator_shift=active_shift
    ).distinct()

    # 2. Encontrar todos los correos que el operador ya envió a aprobación en este turno
    sent_emails_for_companies = Email.objects.filter(
        operator=request.user,
        created_at__gte=active_shift.actual_start_time
    ).values_list('company_id', flat=True)

    # 3. Comparar para encontrar las empresas faltantes
    missing_companies = []
    for company in companies_with_updates:
        if company.id not in sent_emails_for_companies:
            missing_companies.append(company.name)

    # 4. Si faltan empresas, bloquear, notificar y detener la ejecución
    if missing_companies:
        message = f"No puedes finalizar el turno. Faltan correos por generar para las siguientes empresas: {', '.join(missing_companies)}."
        messages.error(request, message)
        return redirect('operator_dashboard')

    # --- FIN DE LA LÓGICA DE VALIDACIÓN ---

    # --- SI LA VALIDACIÓN PASA, SE PROCEDE A GENERAR EL PDF ---
    # (Este es el bloque de código que faltaba)
    
    completed_checklist = ChecklistLog.objects.filter(operator_shift=active_shift)
    updates_log = UpdateLog.objects.filter(operator_shift=active_shift)
    rondas_virtuales = VirtualRoundLog.objects.filter(operator_shift=active_shift)

    context = {
        'operator': request.user,
        'start_time': active_shift.actual_start_time,
        'end_time': timezone.now(),
        'completed_checklist': completed_checklist,
        'updates_log': updates_log,
        'rondas_virtuales': rondas_virtuales,
    }

    template = get_template('turn_report_pdf.html')
    html = template.render(context)
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html.encode("UTF-8")), result)

    if not pdf.err:
        report = TurnReport(operator=request.user, start_time=active_shift.actual_start_time)
        pdf_file = ContentFile(result.getvalue())
        report.pdf_report.save(
            f'reporte_turno_{request.user.username}_{timezone.now().strftime("%Y%m%d%H%M%S")}.pdf',
            pdf_file
        )
        active_shift.actual_end_time = timezone.now()
        active_shift.save()
        return redirect('sign_turn_report', report_id=report.id)

    return HttpResponse("Error al generar el PDF", status=500)

@login_required
def start_virtual_round(request):
    active_shift = get_active_shift(request.user)
    if not active_shift:
        return JsonResponse({'status': 'error', 'message': 'No tienes un turno activo para iniciar una ronda.'}, status=403)
    
    if request.method == 'POST':
        # Se asocia la ronda al TURNO ACTIVO, no solo al operador
        new_round = VirtualRoundLog.objects.create(
            operator_shift=active_shift, 
            start_time=timezone.now()
        )
        request.session['active_round_id'] = new_round.id
        TraceabilityLog.objects.create(user=request.user, action="Inició ronda virtual.")
        return JsonResponse({'status': 'success', 'message': 'Ronda iniciada.'})
    return JsonResponse({'status': 'error'}, status=405)

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
    if request.method == 'POST':
        report.is_signed = True; report.signed_at = timezone.now(); report.save()
        TraceabilityLog.objects.create(user=request.user, action="Firmó y finalizó su reporte de turno.")
        from django.contrib.auth import logout
        logout(request)
        return redirect('login')
    return render(request, 'turn_report_preview.html', {'report': report})

# --- VISTAS AJAX ---
@login_required
def get_updates_for_company(request, company_id):
    installations = Installation.objects.filter(company_id=company_id, updatelog__isnull=False).distinct()
    response_data = []
    for inst in installations:
        updates = UpdateLog.objects.filter(installation=inst).order_by('-created_at')
        updates_list = [{'id': u.id, 'text': f"{u.created_at.strftime('%d/%m %H:%M')} - {u.message}"} for u in updates]
        response_data.append({'installation_name': inst.name, 'updates': updates_list})
    return JsonResponse({'grouped_updates': response_data})

@login_required
def get_service_status(request):
    services = MonitoredService.objects.filter(is_active=True)
    status_list = []
    for s in services:
        latest_log = s.logs.order_by('-timestamp').first()
        status_list.append({'id': s.id, 'name': s.name, 'status': latest_log.is_up if latest_log else None})
    return render(request, '_service_status_panel.html', {'service_status_list': status_list})