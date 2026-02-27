from django import forms
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from ..models import Company, Installation
from ..forms import CompanyForm, InstallationForm
from .auth import is_supervisor


@login_required
@user_passes_test(is_supervisor)
def manage_companies(request):
    companies = Company.objects.all()
    total_installations = Installation.objects.count()
    return render(request, 'admin/companies/list.html', {'companies': companies, 'total_installations': total_installations})


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
    return render(request, 'admin/companies/form.html', {'form': form, 'title': 'Añadir Empresa'})


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
    return render(request, 'admin/companies/form.html', {'form': form, 'title': 'Editar Empresa'})


@login_required
@user_passes_test(is_supervisor)
def delete_company(request, company_id):
    company = get_object_or_404(Company, id=company_id)
    if request.method == 'POST':
        company.delete()
        return redirect('manage_companies')
    return render(request, 'admin/companies/confirm_delete.html', {'company': company})


@login_required
@user_passes_test(is_supervisor)
def manage_installations(request, company_id):
    company = get_object_or_404(Company, id=company_id)
    installations = Installation.objects.filter(company=company)
    return render(request, 'admin/installations/list.html', {'company': company, 'installations': installations})


@login_required
@user_passes_test(is_supervisor)
def create_installation(request, company_id):
    company = get_object_or_404(Company, id=company_id)
    if request.method == 'POST':
        form = InstallationForm(request.POST)
        if form.is_valid():
            inst = form.save(commit=False)
            inst.company = company
            inst.save()
            return redirect('manage_installations', company_id=company.id)
    else:
        form = InstallationForm(initial={'company': company})
        form.fields['company'].widget = forms.HiddenInput()
    return render(request, 'admin/installations/form.html', {
        'form': form,
        'title': f'Añadir Instalación para {company.name}',
        'company': company
    })


@login_required
@user_passes_test(is_supervisor)
def edit_installation(request, installation_id):
    inst = get_object_or_404(Installation, id=installation_id)
    if request.method == 'POST':
        form = InstallationForm(request.POST, instance=inst)
        if form.is_valid():
            form.save()
            return redirect('manage_installations', company_id=inst.company.id)
    else:
        form = InstallationForm(instance=inst)
        form.fields['company'].widget = forms.HiddenInput()
    return render(request, 'admin/installations/form.html', {
        'form': form,
        'title': f'Editar Instalación {inst.name}',
        'company': inst.company
    })


@login_required
@user_passes_test(is_supervisor)
def delete_installation(request, installation_id):
    inst = get_object_or_404(Installation, id=installation_id)
    company_id = inst.company.id
    if request.method == 'POST':
        inst.delete()
        return redirect('manage_installations', company_id=company_id)
    return render(request, 'admin/installations/confirm_delete.html', {'installation': inst})
