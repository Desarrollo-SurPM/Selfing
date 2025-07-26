from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.utils import timezone
from django import forms  # Importación añadida para usar widgets de formulario
from .models import Company, Installation, ChecklistItem, ChecklistLog, UpdateLog, Email, TraceabilityLog
from .forms import (
    UpdateLogForm, EmailForm, OperatorCreationForm, OperatorChangeForm, 
    CompanyForm, InstallationForm, ChecklistItemForm
)

def is_supervisor(user):
    # Por ahora, solo los superusuarios son supervisores.
    return user.is_superuser

@login_required
def home(request):
    if is_supervisor(request.user):
        return redirect('admin_dashboard')
    else:
        return redirect('operator_dashboard')

# --- Vistas de Administrador/Supervisor ---

@login_required
@user_passes_test(is_supervisor)
def admin_dashboard(request):
    reports = UpdateLog.objects.all().order_by('-created_at')
    pending_emails = Email.objects.filter(status='pending').order_by('-created_at')
    traceability_logs = TraceabilityLog.objects.all().order_by('-timestamp')[:20]
    context = {
        'reports': reports,
        'pending_emails': pending_emails,
        'traceability_logs': traceability_logs,
    }
    return render(request, 'admin_dashboard.html', context)

@login_required
@user_passes_test(is_supervisor)
def approve_email(request, email_id):
    email = get_object_or_404(Email, id=email_id)
    email.status = 'approved'
    email.approved_by = request.user
    email.approved_at = timezone.now()
    email.save()
    TraceabilityLog.objects.create(user=request.user, action=f"Aprobó correo para {email.company.name}")
    return redirect('admin_dashboard')

# Vistas de Gestión de Operadores
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
        if form.is_valid():
            form.save()
            return redirect('manage_operators')
    else:
        form = OperatorCreationForm()
    return render(request, 'operator_form.html', {'form': form, 'title': 'Añadir Operador'})

@login_required
@user_passes_test(is_supervisor)
def edit_operator(request, user_id):
    operator = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        form = OperatorChangeForm(request.POST, instance=operator)
        if form.is_valid():
            form.save()
            return redirect('manage_operators')
    else:
        form = OperatorChangeForm(instance=operator)
    return render(request, 'operator_form.html', {'form': form, 'title': 'Editar Operador'})

@login_required
@user_passes_test(is_supervisor)
def delete_operator(request, user_id):
    operator = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        operator.delete()
        return redirect('manage_operators')
    return render(request, 'operator_confirm_delete.html', {'operator': operator})

# Vistas de Gestión de Empresas
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
        if form.is_valid():
            form.save()
            return redirect('manage_companies')
    else:
        form = CompanyForm()
    return render(request, 'company_form.html', {'form': form, 'title': 'Añadir Empresa Cliente'})

@login_required
@user_passes_test(is_supervisor)
def edit_company(request, company_id):
    company = get_object_or_404(Company, id=company_id)
    if request.method == 'POST':
        form = CompanyForm(request.POST, instance=company)
        if form.is_valid():
            form.save()
            return redirect('manage_companies')
    else:
        form = CompanyForm(instance=company)
    return render(request, 'company_form.html', {'form': form, 'title': 'Editar Empresa Cliente'})

@login_required
@user_passes_test(is_supervisor)
def delete_company(request, company_id):
    company = get_object_or_404(Company, id=company_id)
    if request.method == 'POST':
        company.delete()
        return redirect('manage_companies')
    return render(request, 'company_confirm_delete.html', {'company': company})

# Vistas de Gestión de Instalaciones
@login_required
@user_passes_test(is_supervisor)
def manage_installations(request, company_id):
    company = get_object_or_404(Company, id=company_id)
    installations = Installation.objects.filter(company=company)
    context = {
        'company': company,
        'installations': installations
    }
    return render(request, 'manage_installations.html', context)

@login_required
@user_passes_test(is_supervisor)
def create_installation(request, company_id):
    company = get_object_or_404(Company, id=company_id)
    if request.method == 'POST':
        form = InstallationForm(request.POST)
        if form.is_valid():
            installation = form.save(commit=False)
            installation.company = company
            installation.save()
            return redirect('manage_installations', company_id=company.id)
    else:
        form = InstallationForm(initial={'company': company})
        form.fields['company'].widget = forms.HiddenInput()

    context = {
        'form': form, 
        'title': f'Añadir Instalación para {company.name}',
        'company': company
    }
    return render(request, 'installation_form.html', context)

@login_required
@user_passes_test(is_supervisor)
def edit_installation(request, installation_id):
    installation = get_object_or_404(Installation, id=installation_id)
    company = installation.company
    if request.method == 'POST':
        form = InstallationForm(request.POST, instance=installation)
        if form.is_valid():
            form.save()
            return redirect('manage_installations', company_id=company.id)
    else:
        form = InstallationForm(instance=installation)
        form.fields['company'].widget = forms.HiddenInput()

    context = {
        'form': form, 
        'title': f'Editar Instalación {installation.name}',
        'company': company
    }
    return render(request, 'installation_form.html', context)

@login_required
@user_passes_test(is_supervisor)
def delete_installation(request, installation_id):
    installation = get_object_or_404(Installation, id=installation_id)
    company_id = installation.company.id
    if request.method == 'POST':
        installation.delete()
        return redirect('manage_installations', company_id=company_id)
    
    return render(request, 'installation_confirm_delete.html', {'installation': installation})


# Vistas de Gestión de Checklist
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
        if form.is_valid():
            form.save()
            return redirect('manage_checklist_items')
    else:
        form = ChecklistItemForm()
    return render(request, 'checklist_item_form.html', {'form': form, 'title': 'Añadir Tarea al Checklist'})

@login_required
@user_passes_test(is_supervisor)
def edit_checklist_item(request, item_id):
    item = get_object_or_404(ChecklistItem, id=item_id)
    if request.method == 'POST':
        form = ChecklistItemForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            return redirect('manage_checklist_items')
    else:
        form = ChecklistItemForm(instance=item)
    return render(request, 'checklist_item_form.html', {'form': form, 'title': 'Editar Tarea del Checklist'})

@login_required
@user_passes_test(is_supervisor)
def delete_checklist_item(request, item_id):
    item = get_object_or_404(ChecklistItem, id=item_id)
    if request.method == 'POST':
        item.delete()
        return redirect('manage_checklist_items')
    return render(request, 'checklist_item_confirm_delete.html', {'item': item})

# --- Vistas del Operador ---

@login_required
def operator_dashboard(request):
    return render(request, 'operator_dashboard.html')

@login_required
def checklist_view(request):
    if request.method == 'POST':
        item_ids = request.POST.getlist('items')
        for item_id in item_ids:
            item = get_object_or_404(ChecklistItem, id=item_id)
            log, created = ChecklistLog.objects.get_or_create(
                operator=request.user, 
                item=item,
                completed_at__date=timezone.now().date()
            )
            if created:
                TraceabilityLog.objects.create(user=request.user, action=f"Completó checklist: {item.description}")
        return redirect('checklist')

    all_items = ChecklistItem.objects.all()
    completed_ids = ChecklistLog.objects.filter(
        operator=request.user, 
        completed_at__date=timezone.now().date()
    ).values_list('item_id', flat=True)

    context = {
        'items': all_items,
        'completed_ids': completed_ids
    }
    return render(request, 'checklist.html', context)

@login_required
def update_log_view(request):
    if request.method == 'POST':
        form = UpdateLogForm(request.POST)
        if form.is_valid():
            log = form.save(commit=False)
            log.operator = request.user
            log.save()
            TraceabilityLog.objects.create(user=request.user, action=f"Registró novedad para {log.installation}")
            return redirect('operator_dashboard')
    else:
        form = UpdateLogForm()

    # Usamos prefetch_related para cargar todas las instalaciones en una sola consulta
    companies_with_installations = Company.objects.prefetch_related('installations')
    
    context = {
        'form': form,
        'companies': companies_with_installations
    }
    return render(request, 'update_log.html', context)

@login_required
def email_form_view(request):
    if request.method == 'POST':
        form = EmailForm(request.POST, operator=request.user)
        if form.is_valid():
            email = form.save(commit=False)
            email.operator = request.user
            email.status = 'pending'
            email.save()
            form.save_m2m()
            TraceabilityLog.objects.create(user=request.user, action=f"Generó borrador de correo para {email.company.name}")
            return redirect('operator_dashboard')
    else:
        company_id = request.GET.get('company')
        initial_data = {}
        if company_id:
            initial_data['company'] = company_id
        form = EmailForm(initial=initial_data, operator=request.user)
    return render(request, 'email_form.html', {'form': form})