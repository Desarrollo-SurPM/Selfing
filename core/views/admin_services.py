from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from ..models import MonitoredService
from ..forms import MonitoredServiceForm
from .auth import is_supervisor


@login_required
@user_passes_test(is_supervisor)
def manage_monitored_services(request):
    services = MonitoredService.objects.all()
    return render(request, 'admin/services/list.html', {'services': services})


@login_required
@user_passes_test(is_supervisor)
def create_monitored_service(request):
    if request.method == 'POST':
        form = MonitoredServiceForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('manage_monitored_services')
    else:
        form = MonitoredServiceForm()
    return render(request, 'admin/services/form.html', {'form': form, 'title': 'Añadir Servicio a Monitorear'})


@login_required
@user_passes_test(is_supervisor)
def edit_monitored_service(request, service_id):
    service = get_object_or_404(MonitoredService, id=service_id)
    if request.method == 'POST':
        form = MonitoredServiceForm(request.POST, instance=service)
        if form.is_valid():
            form.save()
            return redirect('manage_monitored_services')
    else:
        form = MonitoredServiceForm(instance=service)
    return render(request, 'admin/services/form.html', {'form': form, 'title': 'Editar Servicio Monitoreado'})


@login_required
@user_passes_test(is_supervisor)
def delete_monitored_service(request, service_id):
    service = get_object_or_404(MonitoredService, id=service_id)
    if request.method == 'POST':
        service.delete()
        return redirect('manage_monitored_services')
    return render(request, 'admin/services/confirm_delete.html', {'service': service})
