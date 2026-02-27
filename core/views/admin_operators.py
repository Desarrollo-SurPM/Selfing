from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from ..forms import OperatorCreationForm, OperatorChangeForm
from .auth import is_supervisor


@login_required
@user_passes_test(is_supervisor)
def manage_operators(request):
    operators = User.objects.filter(is_superuser=False)
    return render(request, 'admin/operators/list.html', {'operators': operators})


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
    return render(request, 'admin/operators/form.html', {'form': form, 'title': 'Añadir Operador'})


@login_required
@user_passes_test(is_supervisor)
def edit_operator(request, user_id):
    op = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        form = OperatorChangeForm(request.POST, instance=op)
        if form.is_valid():
            form.save()
            return redirect('manage_operators')
    else:
        form = OperatorChangeForm(instance=op)
    return render(request, 'admin/operators/form.html', {'form': form, 'title': 'Editar Operador'})


@login_required
@user_passes_test(is_supervisor)
def delete_operator(request, user_id):
    op = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        op.delete()
        return redirect('manage_operators')
    return render(request, 'admin/operators/confirm_delete.html', {'operator': op})
