import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.http import JsonResponse
from ..models import ChecklistItem
from ..forms import ChecklistItemForm
from .auth import is_supervisor


@login_required
@user_passes_test(is_supervisor)
def manage_checklist_items(request):
    items = ChecklistItem.objects.all()
    return render(request, 'admin/checklist/list.html', {'items': items})


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
    return render(request, 'admin/checklist/form.html', {'form': form, 'title': 'Añadir Tarea al Checklist'})


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
    return render(request, 'admin/checklist/form.html', {'form': form, 'title': 'Editar Tarea del Checklist'})


@login_required
@user_passes_test(is_supervisor)
def delete_checklist_item(request, item_id):
    item = get_object_or_404(ChecklistItem, id=item_id)
    if request.method == 'POST':
        item.delete()
        return redirect('manage_checklist_items')
    return render(request, 'admin/checklist/confirm_delete.html', {'item': item})


@csrf_exempt
@login_required
@user_passes_test(is_supervisor)
@transaction.atomic
def update_checklist_order(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            item_ids = data.get('order', [])
            for index, item_id in enumerate(item_ids):
                ChecklistItem.objects.filter(pk=item_id).update(order=index)
            return JsonResponse({'status': 'success', 'message': 'Orden actualizado.'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=405)
