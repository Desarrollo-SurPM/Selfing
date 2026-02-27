from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from ..models import EmergencyContact
from ..forms import EmergencyContactForm
from .auth import is_supervisor


@login_required
@user_passes_test(is_supervisor)
def manage_emergency_contacts(request):
    contacts = EmergencyContact.objects.select_related('company', 'installation').all()
    return render(request, 'admin/emergency_contacts/list.html', {'contacts': contacts})


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
    return render(request, 'admin/emergency_contacts/form.html', {'form': form, 'title': 'Añadir Contacto de Emergencia'})


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
    else:
        form = EmergencyContactForm(instance=contact)
    return render(request, 'admin/emergency_contacts/form.html', {'form': form, 'title': 'Editar Contacto de Emergencia'})


@login_required
@user_passes_test(is_supervisor)
def delete_emergency_contact(request, contact_id):
    contact = get_object_or_404(EmergencyContact, id=contact_id)
    if request.method == 'POST':
        contact.delete()
        messages.success(request, "Contacto eliminado.")
        return redirect('manage_emergency_contacts')
    return render(request, 'admin/emergency_contacts/confirm_delete.html', {'contact': contact})
