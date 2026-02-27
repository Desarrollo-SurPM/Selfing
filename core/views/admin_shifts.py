import json
import calendar
from datetime import date, timedelta, datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q
from ..models import ShiftType, OperatorShift, Company
from ..forms import ShiftTypeForm, OperatorShiftForm
from .auth import is_supervisor


@login_required
@user_passes_test(is_supervisor)
def manage_shifts(request):
    today = timezone.now().date()
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    search_query = request.GET.get('q', '')

    if start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            start_date = today.replace(day=1)
            end_date = (start_date + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    else:
        start_date = today.replace(day=1)
        _, last_day = calendar.monthrange(today.year, today.month)
        end_date = today.replace(day=last_day)

    delta = end_date - start_date
    days_range = [start_date + timedelta(days=i) for i in range(delta.days + 1)]

    operators = User.objects.filter(is_superuser=False).order_by('first_name', 'last_name')
    if search_query:
        operators = operators.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(username__icontains=search_query)
        )

    shift_types = ShiftType.objects.all()
    all_companies = Company.objects.all().order_by('name')

    existing_shifts = OperatorShift.objects.filter(
        date__range=[start_date, end_date],
        operator__in=operators
    ).select_related('shift_type').prefetch_related('monitored_companies')

    assignments = {}
    for shift in existing_shifts:
        assignments[(shift.operator_id, shift.date.strftime('%Y-%m-%d'))] = shift

    matrix_rows = []
    for operator in operators:
        row_data = {'operator': operator, 'days': []}
        for day in days_range:
            day_str = day.strftime('%Y-%m-%d')
            shift = assignments.get((operator.id, day_str))
            assigned_company_ids = []
            if shift:
                assigned_company_ids = list(shift.monitored_companies.values_list('id', flat=True))
            row_data['days'].append({'date': day_str, 'shift': shift, 'company_ids': assigned_company_ids})
        matrix_rows.append(row_data)

    context = {
        'current_start_date': start_date.strftime('%Y-%m-%d'),
        'current_end_date': end_date.strftime('%Y-%m-%d'),
        'search_query': search_query,
        'days_range': days_range,
        'matrix_rows': matrix_rows,
        'shift_types': shift_types,
        'all_companies': all_companies,
    }
    return render(request, 'admin/shifts/list.html', context)


@login_required
@user_passes_test(is_supervisor)
@csrf_exempt
def api_update_shift(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            operator_id = data.get('operator_id')
            date_str = data.get('date')
            shift_type_id = data.get('shift_type_id')
            company_ids = data.get('company_ids')

            if not operator_id or not date_str:
                return JsonResponse({'status': 'error', 'message': 'Datos incompletos'}, status=400)

            if shift_type_id:
                shift, created = OperatorShift.objects.update_or_create(
                    operator_id=operator_id,
                    date=date_str,
                    defaults={'shift_type_id': shift_type_id}
                )
                if company_ids is not None:
                    shift.monitored_companies.set(company_ids)
                action = "updated"
            else:
                OperatorShift.objects.filter(operator_id=operator_id, date=date_str).delete()
                action = "deleted"

            return JsonResponse({'status': 'success', 'action': action})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    return JsonResponse({'status': 'error'}, status=405)


@login_required
@user_passes_test(is_supervisor)
def assign_shift(request):
    if request.method == 'POST':
        form = OperatorShiftForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('manage_shifts')
    else:
        form = OperatorShiftForm()
        form.fields['operator'].queryset = User.objects.filter(is_superuser=False)
    return render(request, 'admin/shifts/assign_form.html', {'form': form, 'title': 'Asignar Nuevo Turno'})


@login_required
@user_passes_test(is_supervisor)
def edit_assigned_shift(request, shift_id):
    shift = get_object_or_404(OperatorShift, id=shift_id)
    if request.method == 'POST':
        form = OperatorShiftForm(request.POST, instance=shift)
        if form.is_valid():
            form.save()
            return redirect('manage_shifts')
    else:
        form = OperatorShiftForm(instance=shift)
        form.fields['operator'].queryset = User.objects.filter(is_superuser=False)
    return render(request, 'admin/shifts/assign_form.html', {'form': form, 'title': 'Editar Turno Asignado'})


@login_required
@user_passes_test(is_supervisor)
def delete_assigned_shift(request, shift_id):
    shift = get_object_or_404(OperatorShift, id=shift_id)
    if request.method == 'POST':
        shift.delete()
        return redirect('manage_shifts')
    return render(request, 'admin/shifts/confirm_delete.html', {'assigned_shift': shift})


@login_required
@user_passes_test(is_supervisor)
def shift_matrix_view(request):
    today = timezone.now().date()
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))

    num_days = calendar.monthrange(year, month)[1]
    start_date = date(year, month, 1)
    end_date = date(year, month, num_days)
    days_in_month = [start_date + timedelta(days=i) for i in range(num_days)]

    operators = User.objects.filter(is_superuser=False).order_by('first_name')
    shift_types = ShiftType.objects.all()

    existing_shifts = OperatorShift.objects.filter(
        date__range=[start_date, end_date]
    ).select_related('shift_type')

    assignments = {}
    for shift in existing_shifts:
        assignments[(shift.operator_id, shift.date.strftime('%Y-%m-%d'))] = shift

    matrix_rows = []
    for operator in operators:
        row_data = {'operator': operator, 'days': []}
        for day in days_in_month:
            day_str = day.strftime('%Y-%m-%d')
            shift = assignments.get((operator.id, day_str))
            row_data['days'].append({'date': day_str, 'shift': shift})
        matrix_rows.append(row_data)

    prev_month_date = start_date - timedelta(days=1)
    next_month_date = end_date + timedelta(days=1)

    context = {
        'current_date': start_date,
        'days_in_month': days_in_month,
        'matrix_rows': matrix_rows,
        'shift_types': shift_types,
        'prev_year': prev_month_date.year,
        'prev_month': prev_month_date.month,
        'next_year': next_month_date.year,
        'next_month': next_month_date.month,
    }
    return render(request, 'admin/shifts/matrix.html', context)


@login_required
@user_passes_test(is_supervisor)
def manage_shift_types(request):
    shift_types = ShiftType.objects.all().order_by('start_time')
    return render(request, 'admin/shift_types/list.html', {'shift_types': shift_types})


@login_required
@user_passes_test(is_supervisor)
def create_shift_type(request):
    if request.method == 'POST':
        form = ShiftTypeForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('manage_shift_types')
    else:
        form = ShiftTypeForm()
    return render(request, 'admin/shift_types/form.html', {'form': form, 'title': 'Crear Nuevo Tipo de Turno'})


@login_required
@user_passes_test(is_supervisor)
def edit_shift_type(request, type_id):
    shift_type = get_object_or_404(ShiftType, id=type_id)
    if request.method == 'POST':
        form = ShiftTypeForm(request.POST, instance=shift_type)
        if form.is_valid():
            form.save()
            return redirect('manage_shift_types')
    else:
        form = ShiftTypeForm(instance=shift_type)
    return render(request, 'admin/shift_types/form.html', {'form': form, 'title': f'Editar {shift_type.name}'})


@login_required
@user_passes_test(is_supervisor)
def delete_shift_type(request, type_id):
    shift_type = get_object_or_404(ShiftType, id=type_id)
    if request.method == 'POST':
        shift_type.delete()
        return redirect('manage_shift_types')
    return render(request, 'admin/shift_types/confirm_delete.html', {'shift_type': shift_type})


@login_required
@user_passes_test(is_supervisor)
def shift_calendar_view(request):
    operators = User.objects.filter(is_superuser=False).order_by('username')
    return render(request, 'admin/shifts/calendar.html', {'operators': operators})


@login_required
@user_passes_test(is_supervisor)
def get_shifts_for_calendar(request):
    shifts = OperatorShift.objects.select_related('operator', 'shift_type').all()
    events = []
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
