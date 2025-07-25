from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.utils import timezone
from .models import Company, OperatorProfile, ChecklistItem, ChecklistLog, UpdateLog, Email, TraceabilityLog
from .forms import UpdateLogForm, EmailForm, OperatorCreationForm, OperatorChangeForm, CompanyForm

def is_supervisor(user):
    return user.is_superuser or user.groups.filter(name='Supervisores').exists()

@login_required
def home(request):
    if is_supervisor(request.user):
        return redirect('admin_dashboard')
    else:
        return redirect('operator_dashboard')

# Vistas de Administrador/Supervisor
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

# Vistas del Operador
@login_required
def operator_dashboard(request):
    return render(request, 'operator_dashboard.html')

@login_required
def checklist_view(request):
    items = ChecklistItem.objects.all()
    if request.method == 'POST':
        item_id = request.POST.get('item_id')
        item = get_object_or_404(ChecklistItem, id=item_id)
        ChecklistLog.objects.create(operator=request.user, item=item)
        TraceabilityLog.objects.create(user=request.user, action=f"Completó checklist: {item.description}")
        return redirect('checklist')

    completed_today = ChecklistLog.objects.filter(operator=request.user, completed_at__date=timezone.now().date())
    completed_ids = completed_today.values_list('item_id', flat=True)
    context = {'items': items, 'completed_ids': completed_ids}
    return render(request, 'checklist.html', context)

@login_required
def update_log_view(request):
    if request.method == 'POST':
        form = UpdateLogForm(request.POST)
        if form.is_valid():
            log = form.save(commit=False)
            log.operator = request.user
            log.save()
            TraceabilityLog.objects.create(user=request.user, action=f"Registró novedad para {log.company.name}")
            return redirect('operator_dashboard')
    else:
        form = UpdateLogForm()
    companies = Company.objects.all()
    context = {
        'form': form,
        'companies': companies
    }
    return render(request, 'update_log.html', {'form': form})

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