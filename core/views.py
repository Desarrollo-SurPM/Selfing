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
from django.db.models import (
    Q, Min, Max, Count, TimeField, Case, When, DateTimeField, F, Value, ExpressionWrapper, DateField, Avg
)
from collections import defaultdict
from django.contrib import messages
from django.db.models.functions import ExtractHour, ExtractWeekDay, ExtractMonth
import calendar
from io import BytesIO
from django.db import transaction
from django.core.files.base import ContentFile
from django import forms
from datetime import date, timedelta, datetime, time
from collections import defaultdict
from django.contrib.auth import logout
from collections import OrderedDict
import json
from django.views.decorators.csrf import csrf_exempt 
import re # Importar el módulo de expresiones regulares
from django.db.models.functions import Coalesce, Cast
from django.db.models import TimeField
from django.core.mail import EmailMultiAlternatives # <--- Importante
import mimetypes # <--- Importante para detectar si es png/jpg/pdf

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
    ahora = timezone.now()
    
    # --- LÓGICA DE CICLO OPERATIVO (Mantener igual) ---
    today_at_8_30 = ahora.replace(hour=8, minute=30, second=0, microsecond=0)
    if ahora.time() < time(8, 30):
        start_of_operational_day = today_at_8_30 - timedelta(days=1)
    else:
        start_of_operational_day = today_at_8_30
    
    # Rangos de tiempo para el gráfico de Ritmo
    start_of_today = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_week = ahora - timedelta(days=7)   # Últimos 7 días
    start_of_month = ahora - timedelta(days=30) # Últimos 30 días

    # --- CONTADORES PRINCIPALES (Mantener igual) ---
    novedades_hoy = UpdateLog.objects.filter(created_at__gte=start_of_operational_day).count()
    reportes_finalizados_count = TurnReport.objects.filter(is_signed=True, signed_at__gte=start_of_operational_day).count()
    operadores_en_turno = OperatorShift.objects.filter(actual_start_time__isnull=False, actual_end_time__isnull=True).count()
    servicios_monitoreados_activos = MonitoredService.objects.filter(is_active=True).count()
    
    # --- LISTAS Y TABLAS ---
    traceability_logs = TraceabilityLog.objects.select_related('user').all().order_by('-timestamp')[:6]
    reports = UpdateLog.objects.filter(created_at__gte=start_of_operational_day).select_related(
        'operator_shift__operator', 'installation__company'
    ).order_by('-created_at')
    
    # Correos pendientes (necesario para el panel lateral)
    pending_emails = Email.objects.filter(status='pending').select_related('company', 'operator').order_by('-created_at')[:5]

    # ================= DATOS PARA GRÁFICOS =================

    # 1. TIEMPO MEDIO DE RONDAS (En Minutos)
    round_stats = VirtualRoundLog.objects.filter(
        start_time__gte=start_of_month,
        duration_seconds__lt=3600  # Ignorar anomalías > 1 hora
    ).values('operator_shift__operator__username').annotate(
        avg_duration=Avg('duration_seconds')
    ).order_by('avg_duration')

    # Convertir a minutos (dividido por 60) y redondear a 1 decimal
    r_labels = [x['operator_shift__operator__username'] for x in round_stats]
    r_data = [round((x['avg_duration'] or 0) / 60, 1) for x in round_stats]

    # 2. RITMO DE NOVEDADES (Patrón de 24 Horas)
    
    def get_hourly_pattern(start_date):
        """Helper para obtener distribución por hora desde una fecha dada."""
        # Agrupar por hora (0-23)
        qs = UpdateLog.objects.filter(created_at__gte=start_date).annotate(
            hour=ExtractHour('created_at')
        ).values('hour').annotate(count=Count('id')).order_by('hour')
        
        # Convertir a diccionario para búsqueda rápida {hora: cantidad}
        data_dict = {x['hour']: x['count'] for x in qs}
        
        # Generar lista ordenada de 0 a 23, rellenando con 0 si no hay datos
        return [data_dict.get(h, 0) for h in range(24)]

    # Obtener los 3 sets de datos
    pattern_today = get_hourly_pattern(start_of_today)
    pattern_week = get_hourly_pattern(start_of_week)
    pattern_month = get_hourly_pattern(start_of_month)
    
    # Etiquetas del eje X (00:00 a 23:00)
    hours_labels = [f"{h:02d}:00" for h in range(24)]

    # 3. GRÁFICO EXTRA: CARGA POR EMPRESA (Top 5)
    company_stats = UpdateLog.objects.filter(created_at__gte=start_of_month).values(
        'installation__company__name'
    ).annotate(total=Count('id')).order_by('-total')[:5]

    context = {
        # Contadores
        'novedades_hoy': novedades_hoy,
        'reportes_finalizados_count': reportes_finalizados_count,
        'operadores_en_turno': operadores_en_turno,
        'servicios_monitoreados_activos': servicios_monitoreados_activos,
        'reports': reports,
        'traceability_logs': traceability_logs,
        'pending_emails': pending_emails, 

        # Datos Gráfico Rondas (Minutos)
        'chart_rounds_labels': json.dumps(r_labels),
        'chart_rounds_data': json.dumps(r_data),

        # Datos Gráfico Ritmo (Eje X Fijo: Horas)
        'chart_rhythm_labels': json.dumps(hours_labels),
        'chart_rhythm_today': json.dumps(pattern_today),
        'chart_rhythm_week': json.dumps(pattern_week),
        'chart_rhythm_month': json.dumps(pattern_month),

        # Datos Gráfico Empresas
        'chart_comp_labels': json.dumps([x['installation__company__name'] for x in company_stats]),
        'chart_comp_data': json.dumps([x['total'] for x in company_stats]),
    }
    return render(request, 'admin_dashboard.html', context)

# VISTA ACTUALIZADA
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
from datetime import timedelta, datetime, time, date
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.db import transaction
from django.contrib.auth.decorators import login_required, user_passes_test
# Asegúrate de importar tus modelos y formularios aquí
from .models import Company, OperatorShift, UpdateLog, TraceabilityLog, Email
from .forms import AdminUpdateLogForm
import os

def calculate_log_datetime(log):
    """
    Calcula la fecha cronológica exacta para ordenar el reporte.
    Maneja correctamente:
    - Turnos noche (cruce de medianoche).
    - Novedades ingresadas ANTES del inicio del turno (pre-shift).
    - Conversión de zona horaria para logs automáticos.
    """
    # 1. Obtener la hora del evento corregida
    if log.manual_timestamp:
        event_time = log.manual_timestamp
    else:
        # IMPORTANTE: Convertir a hora local antes de extraer el tiempo
        # De lo contrario, usará UTC y el orden será incorrecto.
        event_time = timezone.localtime(log.created_at).time()
    
    # 2. Datos del turno
    shift = log.operator_shift
    base_date = shift.date           # Fecha nominal del turno (ej: 10/01)
    start = shift.shift_type.start_time
    end = shift.shift_type.end_time

    # 3. Lógica para Turnos que cruzan medianoche (Noche)
    # Ej: Inicia 23:00 -> Termina 07:00
    if start > end:
        # A) Madrugada del día siguiente (00:00 - 07:00)
        if event_time <= end:
            return datetime.combine(base_date + timedelta(days=1), event_time)
        
        # B) Noche del día actual (23:00 - 23:59)
        elif event_time >= start:
            return datetime.combine(base_date, event_time)
            
        # C) HORA "LIMBO" (fuera del rango oficial del turno)
        # Aquí solucionamos el problema de las 22:04 en un turno de las 23:00
        else:
            # Si es PM (tarde/noche), asumimos que es llegada anticipada -> DÍA ACTUAL
            if event_time.hour >= 12:
                return datetime.combine(base_date, event_time)
            # Si es AM (mañana), asumimos que es salida tardía -> DÍA SIGUIENTE
            else:
                return datetime.combine(base_date + timedelta(days=1), event_time)
            
    # 4. Lógica para Turnos de Día (ej: 08:00 -> 20:00)
    else:
        # Caso especial: Hora de madrugada (ej: 01:00 AM) en turno de día
        # Significa que se quedaron muy tarde -> Día siguiente
        if event_time < start and event_time.hour < 12:
             return datetime.combine(base_date + timedelta(days=1), event_time)
        
        return datetime.combine(base_date, event_time)

# --- Vista Principal Corregida ---
@login_required
@user_passes_test(lambda u: u.is_superuser)
def review_and_send_novedades(request):
    """
    Gestiona el envío de novedades con ordenamiento cronológico corregido en Python.
    """
    # --- 1. LÓGICA DE CICLO ---
    CUTOFF_TIME = time(8, 30)
    ahora = timezone.now()
    today_at_cutoff = ahora.replace(hour=CUTOFF_TIME.hour, minute=CUTOFF_TIME.minute, second=0, microsecond=0)

    if ahora.time() < CUTOFF_TIME:
        end_of_cycle = today_at_cutoff - timedelta(days=1)
    else:
        end_of_cycle = today_at_cutoff
    
    start_of_cycle = end_of_cycle - timedelta(days=1)

    cycle_shifts_qs = OperatorShift.objects.filter(
        actual_start_time__gte=start_of_cycle,
        actual_start_time__lt=end_of_cycle
    ).select_related('operator', 'shift_type').order_by('actual_start_time')

    # Validaciones iniciales
    if not cycle_shifts_qs.exists():
        messages.info(request, "Aún no ha finalizado un ciclo de turnos para generar un reporte.")
        return render(request, 'review_and_send.html', {
            'companies': None, 
            'add_novedad_form': AdminUpdateLogForm(cycle_shifts=cycle_shifts_qs)
        })

    next_shift_after_cycle = OperatorShift.objects.filter(actual_start_time__gte=end_of_cycle).first()
    if next_shift_after_cycle and next_shift_after_cycle.actual_end_time is not None:
        messages.info(request, "El periodo para enviar el reporte del ciclo anterior ha finalizado.")
        return render(request, 'review_and_send.html', {
            'companies': None, 
            'add_novedad_form': AdminUpdateLogForm(cycle_shifts=OperatorShift.objects.none())
        })
    
    form_to_render = None

    # --- 2. LÓGICA POST ---
    if request.method == 'POST':
        # --- A. AGREGAR NOVEDAD MANUAL ---
        if 'action' in request.POST and request.POST['action'] == 'add_novedad':
            form = AdminUpdateLogForm(request.POST, request.FILES, cycle_shifts=cycle_shifts_qs)
            if form.is_valid():
                selected_shift = form.cleaned_data.get('target_shift')
                if selected_shift and cycle_shifts_qs.filter(pk=selected_shift.pk).exists():
                    new_log = form.save(commit=False)
                    new_log.operator_shift = selected_shift
                    new_log.save()
                    messages.success(request, f'Novedad agregada al turno de {selected_shift.operator.username}.')
                else:
                    messages.error(request, 'El turno seleccionado no es válido.')
                
                # Redirección inteligente para no perder la vista actual
                company_id_redirect = request.POST.get('company_id_for_redirect', '')
                if company_id_redirect:
                    return redirect(f"{request.path}?company_id={company_id_redirect}")
                return redirect('review_and_send_novedades')
            else:
                messages.error(request, 'Error al agregar la novedad.')
                form_to_render = form
        
        # --- B. ENVIAR CORREO (AQUÍ ESTÁ LA CORRECCIÓN DE ORDEN) ---
        elif 'confirm_send' in request.POST:
            company_id_form = request.POST.get('company_id')
            company = get_object_or_404(Company, id=company_id_form)
            selected_ids = request.POST.getlist('updates_to_send')
            observations = request.POST.get('observations', '')

            # 1. Procesar ediciones de texto
            with transaction.atomic():
                 for update_id in selected_ids:
                    new_message = request.POST.get(f'message_{update_id}')
                    if new_message is not None:
                        try:
                            log_to = UpdateLog.objects.get(id=update_id)
                            if log_to.message != new_message:
                                if not log_to.original_message and not log_to.is_edited:
                                     log_to.original_message = log_to.message
                                log_to.message = new_message
                                log_to.is_edited = True
                                log_to.edited_at = timezone.now()
                                log_to.save()
                        except UpdateLog.DoesNotExist:
                            continue

            # 2. OBTENER Y ORDENAR (Corrección Definitiva)
            # Traemos los datos sin orden específico de SQL para no confundirnos
            updates_qs = UpdateLog.objects.filter(id__in=selected_ids).select_related(
                'operator_shift__shift_type', 'installation', 'operator_shift'
            )
            
            # Convertimos a lista Python
            updates_list = list(updates_qs)

            # ORDENAMOS EN PYTHON:
            # Primero por Instalación (A-Z)
            # Segundo por Fecha Real calculada (Ascendente: 22:00 -> 23:00 -> 00:01)
            updates_list.sort(key=lambda x: (x.installation.name, calculate_log_datetime(x)))

            # 3. Construcción del correo
            email_string = company.email or ""
            recipient_list = [email.strip() for email in email_string.split(',') if email.strip()]

            if recipient_list:
                try:
                    protocol = 'https' if request.is_secure() else 'http'
                    domain = request.get_host()
                    base_url = f"{protocol}://{domain}"
                    
                    email_context = {
                        'company': company,
                        'updates': updates_list, # Lista ordenada
                        'observations': observations,
                        'enviado_por': request.user,
                        'cycle_start': start_of_cycle,
                        'cycle_end': end_of_cycle,
                        'base_url': base_url,
                    }
                    
                    html_content = render_to_string('emails/reporte_novedades.html', email_context)
                    subject = f"Reporte de Novedades - {company.name} - {end_of_cycle.strftime('%d/%m/%Y')}"
                    
                    msg = EmailMultiAlternatives(subject, "Reporte HTML", None, recipient_list)
                    msg.attach_alternative(html_content, "text/html")

                    # Adjuntar imágenes
                    count_imgs = 0
                    for update in updates_list:
                        if update.attachment and os.path.exists(update.attachment.path):
                            try:
                                msg.attach_file(update.attachment.path)
                                count_imgs += 1
                            except Exception:
                                pass

                    msg.send()
                    
                    UpdateLog.objects.filter(id__in=selected_ids).update(is_sent=True)
                    TraceabilityLog.objects.create(user=request.user, action=f"Envió correo a {company.name} ({count_imgs} imgs).")
                    messages.success(request, f"Correo enviado a {company.name}.")
                except Exception as e:
                    messages.error(request, f"Error al enviar: {e}")
            else:
                messages.warning(request, f"{company.name} no tiene correo.")

            return redirect('review_and_send_novedades')
    
    # --- FIN LÓGICA POST ---

    if form_to_render is None:
        form_to_render = AdminUpdateLogForm(cycle_shifts=cycle_shifts_qs)

    # --- LÓGICA GET (VISTA PREVIA) ---
    company_id = request.GET.get('company_id')
    selected_company = None
    novedades_pendientes = None # Inicializamos como None
    
    # Base Query: Novedades NO enviadas de los turnos del ciclo
    base_qs = UpdateLog.objects.filter(
        is_sent=False,
        operator_shift__in=cycle_shifts_qs
    ).select_related('installation__company', 'operator_shift__shift_type', 'operator_shift')

    # Lista de empresas para el menú lateral
    company_ids = base_qs.values_list('installation__company_id', flat=True).distinct()
    companies_with_pending_updates = Company.objects.filter(id__in=company_ids).order_by('name')

    if company_id:
        try:
            selected_company = companies_with_pending_updates.get(id=int(company_id))
            
            # 1. Filtramos por la empresa seleccionada
            raw_updates = list(base_qs.filter(installation__company=selected_company))
            
            # 2. APLICAMOS EL MISMO ORDENAMIENTO QUE EN EL CORREO
            # Esto asegura que lo que ves en pantalla sea idéntico a lo que se envía.
            raw_updates.sort(key=lambda x: (x.installation.name, calculate_log_datetime(x)))
            
            novedades_pendientes = raw_updates

        except (Company.DoesNotExist, ValueError):
            selected_company = None

    context = {
        'companies': companies_with_pending_updates,
        'selected_company': selected_company,
        'novedades_pendientes': novedades_pendientes, # Lista Python Ordenada
        'cycle_end': end_of_cycle,
        'start_of_cycle': start_of_cycle,
        'add_novedad_form': form_to_render,
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

@login_required
@user_passes_test(is_supervisor)
def manage_shifts(request):
    # 1. Lógica de Fechas (Rango Personalizado o Mes Actual)
    today = timezone.now().date()
    
    # Obtenemos parámetros GET
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    search_query = request.GET.get('q', '')

    if start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            # Fallback si las fechas son inválidas
            start_date = today.replace(day=1)
            end_date = (start_date + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    else:
        # Por defecto: Mes actual completo
        start_date = today.replace(day=1)
        # Último día del mes actual
        _, last_day = calendar.monthrange(today.year, today.month)
        end_date = today.replace(day=last_day)

    # Generamos la lista de días para las columnas
    delta = end_date - start_date
    days_range = [start_date + timedelta(days=i) for i in range(delta.days + 1)]

    # 2. Filtrado de Operadores
    operators = User.objects.filter(is_superuser=False).order_by('first_name', 'last_name')
    
    if search_query:
        # Busca por nombre, apellido o usuario
        operators = operators.filter(
            Q(first_name__icontains=search_query) | 
            Q(last_name__icontains=search_query) | 
            Q(username__icontains=search_query)
        )

    shift_types = ShiftType.objects.all()
    all_companies = Company.objects.all().order_by('name')

    # 3. Obtener asignaciones (Optimizado)
    existing_shifts = OperatorShift.objects.filter(
        date__range=[start_date, end_date],
        operator__in=operators # Solo traemos turnos de los operadores filtrados
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

            row_data['days'].append({
                'date': day_str,
                'shift': shift,
                'company_ids': assigned_company_ids
            })
        matrix_rows.append(row_data)

    context = {
        'current_start_date': start_date.strftime('%Y-%m-%d'),
        'current_end_date': end_date.strftime('%Y-%m-%d'),
        'search_query': search_query,
        'days_range': days_range, # Usamos la nueva variable de rango
        'matrix_rows': matrix_rows,
        'shift_types': shift_types,
        'all_companies': all_companies,
    }
    return render(request, 'manage_shifts.html', context)
# --- API ACTUALIZADA ---
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
            
            # Recibimos la lista de empresas (opcional)
            company_ids = data.get('company_ids') 

            if not operator_id or not date_str:
                return JsonResponse({'status': 'error', 'message': 'Datos incompletos'}, status=400)

            if shift_type_id:
                # Crear o actualizar turno
                shift, created = OperatorShift.objects.update_or_create(
                    operator_id=operator_id,
                    date=date_str,
                    defaults={'shift_type_id': shift_type_id}
                )
                
                # --- Lógica de Empresas ---
                # Si company_ids no es None, significa que estamos actualizando las empresas.
                # Si es None, no tocamos las empresas (mantiene las que tenía o todas por defecto).
                if company_ids is not None:
                    shift.monitored_companies.set(company_ids)
                
                action = "updated"
            else:
                # Borrar turno
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

def get_operator_companies(operator_user):
    """
    Devuelve el QuerySet de empresas que el operador debe ver en su turno actual.
    """
    active_shift = get_active_shift(operator_user) # Tu función actual en views.py
    
    if not active_shift:
        return Company.objects.none()
    
    # Si tiene empresas específicas asignadas, devolvemos solo esas
    if active_shift.monitored_companies.exists():
        return active_shift.monitored_companies.all()
    
    # Si no, devolvemos todas
    return Company.objects.all()
# --- VISTAS PARA GESTIONAR LOS TIPOS DE TURNO ---

@login_required
@user_passes_test(is_supervisor)
def shift_matrix_view(request):
    # 1. Determinar el mes y año a visualizar (por defecto el actual)
    today = timezone.now().date()
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))
    
    # Calcular fechas del mes
    num_days = calendar.monthrange(year, month)[1]
    start_date = date(year, month, 1)
    end_date = date(year, month, num_days)
    days_in_month = [start_date + timedelta(days=i) for i in range(num_days)]

    # 2. Obtener datos base
    operators = User.objects.filter(is_superuser=False).order_by('first_name')
    shift_types = ShiftType.objects.all()
    
    # 3. Obtener turnos existentes en ese rango optimizado
    existing_shifts = OperatorShift.objects.filter(
        date__range=[start_date, end_date]
    ).select_related('shift_type')

    # 4. Crear estructura de diccionario para acceso rápido: assignments[(user_id, date_str)] = shift_obj
    assignments = {}
    for shift in existing_shifts:
        assignments[(shift.operator_id, shift.date.strftime('%Y-%m-%d'))] = shift

    # 5. Preparar datos para el template
    matrix_rows = []
    for operator in operators:
        row_data = {
            'operator': operator,
            'days': []
        }
        for day in days_in_month:
            day_str = day.strftime('%Y-%m-%d')
            shift = assignments.get((operator.id, day_str))
            row_data['days'].append({
                'date': day_str,
                'shift': shift, # Puede ser None si no hay turno
            })
        matrix_rows.append(row_data)

    # Navegación de meses
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
    return render(request, 'manage_shifts_matrix.html', context)

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
    Usa cálculo de diferencial de tiempo para ser exacto con los 30 minutos.
    """
    if request.method == 'POST':
        shift_to_start = get_active_shift(request.user)

        if shift_to_start and shift_to_start.actual_start_time is None:
            
            # --- VALIDACIÓN ROBUSTA DE 30 MINUTOS ---
            # 1. Obtenemos la zona horaria actual configurada (Santiago)
            current_tz = timezone.get_current_timezone()
            
            # 2. Construimos la fecha/hora de inicio programada (Naive)
            scheduled_naive = datetime.combine(shift_to_start.date, shift_to_start.shift_type.start_time)
            
            # 3. La convertimos a Aware (con zona horaria) para poder restar con 'now'
            if timezone.is_naive(scheduled_naive):
                scheduled_start = timezone.make_aware(scheduled_naive, current_tz)
            else:
                scheduled_start = scheduled_naive

            # 4. Obtenemos la hora actual
            now = timezone.now()

            # 5. Calculamos cuánto falta para el turno
            # Si el turno es a las 08:30 y son las 02:16, time_difference será aprox 6 horas.
            # Si el turno fue ayer, time_difference será negativo.
            time_difference = scheduled_start - now

            # 6. La Condición: Si faltan MÁS de 30 minutos (timedelta > 30 min), bloqueamos.
            # Esto permite iniciar turnos pasados (diferencia negativa) o próximos (diferencia < 30 min).
            if time_difference > timedelta(minutes=30):
                # Calculamos la hora exacta de habilitación para mostrarla en el mensaje
                allowed_entry_time = scheduled_start - timedelta(minutes=30)
                messages.error(
                    request, 
                    f"Es muy temprano. Podrás iniciar turno a partir de las {allowed_entry_time.strftime('%H:%M')} (30 min antes)."
                )
                return redirect('operator_dashboard')
            # -----------------------------------------------------

            # Si pasa la validación, iniciamos
            shift_to_start.actual_start_time = now
            shift_to_start.save()
            
            # Registro de trazabilidad
            TraceabilityLog.objects.create(
                user=request.user, 
                action="Inició turno."
            )
            
            messages.success(request, f"Turno '{shift_to_start.shift_type.name}' iniciado correctamente.")
        
        elif shift_to_start and shift_to_start.actual_start_time is not None:
            messages.warning(request, "El turno ya se encuentra iniciado.")
        
        else:
            messages.error(request, "No se pudo encontrar un turno pendiente para iniciar.")

    return redirect('operator_dashboard')

@login_required
def operator_dashboard(request):
    active_shift = get_active_shift(request.user)
    active_notes = ShiftNote.objects.filter(is_active=True)
    
    # Formulario para crear notas de turno desde el modal
    shift_note_form = ShiftNoteForm()

    # --- LÓGICA DE BLOQUEO VISUAL (NUEVO) ---
    start_blocked = False
    allowed_start_time = None

    # Si hay turno pero no ha iniciado, verificamos la hora
    if active_shift and not active_shift.actual_start_time:
        try:
            current_tz = timezone.get_current_timezone()
            # Combinamos fecha del turno + hora de inicio
            scheduled_naive = datetime.combine(active_shift.date, active_shift.shift_type.start_time)
            
            # Aseguramos zona horaria
            if timezone.is_naive(scheduled_naive):
                scheduled_start = timezone.make_aware(scheduled_naive, current_tz)
            else:
                scheduled_start = scheduled_naive
            
            # Calculamos hora permitida (30 min antes)
            allowed_start_time = scheduled_start - timedelta(minutes=30)
            
            # Si ahora es antes de la hora permitida -> BLOQUEADO
            if timezone.now() < allowed_start_time:
                start_blocked = True
        except Exception as e:
            # En caso de error de fechas, no bloqueamos por seguridad
            print(f"Error calculando bloqueo: {e}")
    # ----------------------------------------
    
    # Preparamos un contexto base
    context = {
        'active_shift': active_shift,
        'active_notes': active_notes,
        'shift_note_form': shift_note_form,
        'start_blocked': start_blocked,           # <-- Variable nueva
        'allowed_start_time': allowed_start_time, # <-- Variable nueva
    }

    # Si el turno ya ha sido iniciado, calculamos todo el progreso y las tareas.
    if active_shift and active_shift.actual_start_time:
        progress_tasks = {}
        completed_tasks_count = 0
        total_tasks = 2 
        
        # 1. Lógica de Progreso - RONDAS
        total_rondas_requeridas = 7
        rondas_completadas = VirtualRoundLog.objects.filter(operator_shift=active_shift).count()
        progress_tasks['rondas'] = {'completed': (rondas_completadas >= total_rondas_requeridas), 'text': f"Rondas ({rondas_completadas}/{total_rondas_requeridas})"}
        if progress_tasks['rondas']['completed']: completed_tasks_count += 1

        # --- MODIFICACIÓN: BITÁCORA DINÁMICA ---
        # Determinamos qué empresas debe monitorear este turno específico
        if active_shift.monitored_companies.exists():
            # Si hay empresas específicas seleccionadas en el turno
            empresas_objetivo = active_shift.monitored_companies.filter(installations__isnull=False).distinct()
        else:
            # Si está vacío, son TODAS las empresas
            empresas_objetivo = Company.objects.filter(installations__isnull=False).distinct()
            
        # Contamos en cuántas de esas empresas objetivo ha escrito novedades
        ids_empresas_con_log = UpdateLog.objects.filter(
            operator_shift=active_shift,
            installation__company__in=empresas_objetivo # Filtramos solo logs de las empresas objetivo
        ).values_list('installation__company_id', flat=True).distinct()
        
        # Calculamos el progreso basado en las empresas objetivo
        progress_tasks['bitacora'] = {
            'completed': (len(ids_empresas_con_log) >= empresas_objetivo.count()), 
            'text': f"Bitácora ({len(ids_empresas_con_log)}/{empresas_objetivo.count()})"
        }
        if progress_tasks['bitacora']['completed']: completed_tasks_count += 1
        # --- FIN MODIFICACIÓN ---
        
        context['progress_percentage'] = int((completed_tasks_count / total_tasks) * 100) if total_tasks > 0 else 0
        context['progress_tasks'] = progress_tasks
        
        # ... (El resto de la vista, Lógica de Alarma, Logs, Timer, se mantiene igual) ...
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
        
        context['round_completed_this_cycle'] = round_completed_this_cycle
        context['shift_start_time_iso'] = active_shift.actual_start_time.isoformat()
    
    return render(request, 'operator_dashboard.html', context)

@login_required
def my_logbook_view(request):
    """
    Muestra al operador un resumen de sus novedades.
    VERSIÓN CORREGIDA: Ordenamiento cronológico real usando Python.
    """
    active_shift = get_active_shift(request.user)
    
    # Si no hay turno activo, devolvemos un diccionario vacío.
    if not active_shift:
        return render(request, 'my_logbook.html', {'logbook_data': {}})

    # 1. Traemos los datos SIN ordenar por DB (para no confundir la lógica)
    logs_del_turno_qs = UpdateLog.objects.filter(
        operator_shift=active_shift
    ).select_related('installation', 'installation__company')

    # 2. Convertimos a lista y ORDENAMOS CON PYTHON
    # Clave de orden: 
    #  A) Nombre Empresa (para agrupar visualmente)
    #  B) Nombre Instalación 
    #  C) Fecha/Hora REAL calculada (Aquí es donde se arregla el 23:10 vs 00:01)
    logs_list = list(logs_del_turno_qs)
    logs_list.sort(key=lambda x: (
        x.installation.company.name, 
        x.installation.name, 
        calculate_log_datetime(x)
    ))

    # 3. Agrupamos los datos (Iteramos la lista YA ORDENADA)
    logbook_data = {}
    for log in logs_list:
        if log.installation and log.installation.company:
            company_name = log.installation.company.name
            installation_name = log.installation.name
            
            # Crear claves si no existen
            if company_name not in logbook_data:
                logbook_data[company_name] = {}
            
            if installation_name not in logbook_data[company_name]:
                logbook_data[company_name][installation_name] = []
            
            # Como logs_list ya está ordenada cronológicamente, el append mantiene el orden
            logbook_data[company_name][installation_name].append(log)

    context = {
        'logbook_data': logbook_data,
        'shift_start_time': active_shift.actual_start_time
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
        form = UpdateLogEditForm(request.POST, request.FILES, instance=log_entry)
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
        form = UpdateLogForm(request.POST, request.FILES)
        if form.is_valid():
            new_log = form.save(commit=False)
            new_log.operator_shift = active_shift
            
            # --- VALIDACIÓN DE SEGURIDAD EXTRA ---
            # Asegurarse que no estén intentando guardar en una empresa no permitida (hackeando el HTML)
            if active_shift.monitored_companies.exists():
                company = new_log.installation.company
                if not active_shift.monitored_companies.filter(id=company.id).exists():
                    messages.error(request, "No tienes permiso para registrar novedades en esta empresa durante este turno.")
                    return redirect('update_log')
            # -------------------------------------

            new_log.save()
            messages.success(request, 'Novedad registrada con éxito en la bitácora.')
            return redirect('update_log')
        else:
            messages.error(request, 'Hubo un error al guardar la novedad. Por favor, revisa los datos.')

    # 3. Preparamos los datos para mostrar la página por primera vez (GET).
    form = UpdateLogForm()
    
    # --- MODIFICACIÓN: FILTRAR EMPRESAS ---
    if active_shift.monitored_companies.exists():
        # Si el turno tiene restricciones, solo traemos esas empresas
        companies_qs = active_shift.monitored_companies.all()
    else:
        # Si no, traemos todas
        companies_qs = Company.objects.all()
        
    # Usamos prefetch_related sobre el queryset filtrado
    companies_with_installations = companies_qs.prefetch_related('installations')
    # --- FIN MODIFICACIÓN ---

    context = {
        'form': form,
        'companies': companies_with_installations 
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

    # --- Lógica de validación ---
    validation_errors = []
    total_rondas_requeridas = 7
    rondas_completadas = VirtualRoundLog.objects.filter(operator_shift=active_shift).count()
    if rondas_completadas < total_rondas_requeridas:
        faltantes = total_rondas_requeridas - rondas_completadas
        validation_errors.append(f"Faltan {faltantes} rondas virtuales por completar.")

    # --- MODIFICACIÓN: VALIDACIÓN DINÁMICA DE EMPRESAS ---
    # 1. Definir qué empresas se requieren
    if active_shift.monitored_companies.exists():
        empresas_requeridas = active_shift.monitored_companies.filter(installations__isnull=False).distinct()
    else:
        empresas_requeridas = Company.objects.filter(installations__isnull=False).distinct()

    # 2. Obtener empresas donde SÍ se escribió
    ids_empresas_con_log = UpdateLog.objects.filter(operator_shift=active_shift).values_list('installation__company_id', flat=True).distinct()
    
    # 3. Comparar requeridas vs escritas
    empresas_faltantes_bitacora = [c.name for c in empresas_requeridas if c.id not in ids_empresas_con_log]
    
    if empresas_faltantes_bitacora:
        validation_errors.append(f"Falta registrar en bitácora para: {', '.join(empresas_faltantes_bitacora)}.")
    # --- FIN MODIFICACIÓN ---
    
    if validation_errors:
        full_error_message = "No puedes finalizar el turno. Tareas pendientes: " + " ".join(validation_errors)
        messages.error(request, full_error_message)
        return redirect('operator_dashboard')

    end_time = timezone.now()
    # ... (El resto de la vista se mantiene igual: calculo de duración, generación de PDF, etc.) ...
    duration_timedelta = end_time - active_shift.actual_start_time
    total_seconds = int(duration_timedelta.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    formatted_duration = f"{hours}h {minutes}m"

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
        logs_for_phase = completed_checklist_qs.filter(item__phase=phase_key)
        if logs_for_phase.exists():
            checklist_by_phase[phase_key] = {
                'display_name': phase_display_names.get(phase_key),
                'logs': logs_for_phase
            }

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
        'checklist_by_phase': checklist_by_phase,
        'updates_log': updates_log,
        'rondas_virtuales': rondas_virtuales,
    }

    template = get_template('turn_report_pdf.html')
    html = template.render(context)
    result = BytesIO()
    pdf = pisa.pisaDocument(
        BytesIO(html.encode("UTF-8")),
        result,
        link_callback=link_callback 
    )

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
    # Obtener la ronda asegurando que pertenece al usuario
    active_round = get_object_or_404(VirtualRoundLog, id=round_id, operator_shift__operator=request.user)
    active_shift = active_round.operator_shift
    
    # --- Lógica de Filtrado de Instalaciones ---
    # Si el turno tiene empresas específicas, solo mostramos esas.
    # Si no tiene (es turno completo), mostramos todas.
    if active_shift.monitored_companies.exists():
        allowed_installations = Installation.objects.filter(
            company__in=active_shift.monitored_companies.all()
        ).order_by('company__name', 'name')
    else:
        allowed_installations = Installation.objects.all().order_by('company__name', 'name')
    # -------------------------------------------

    # Detectar si es una petición AJAX (para el modal)
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if request.method == 'POST':
        form = VirtualRoundCompletionForm(request.POST, instance=active_round, installations_queryset=allowed_installations)
        if form.is_valid():
            # Procesar las instalaciones seleccionadas
            installations = form.cleaned_data['checked_installations']
            active_round.checked_installations = ", ".join([inst.name for inst in installations])
            
            # Calcular tiempos y cerrar la ronda
            end_time = timezone.now()
            duration = end_time - active_round.start_time
            active_round.end_time = end_time
            active_round.duration_seconds = duration.total_seconds()
            active_round.save()
            
            # Formato de duración para el log
            total_seconds = int(duration.total_seconds())
            minutes, seconds = divmod(total_seconds, 60)
            formatted_duration = f"{minutes} min {seconds} seg"
            
            # Registrar en trazabilidad
            TraceabilityLog.objects.create(
                user=request.user, 
                action=f"Finalizó ronda virtual. Duración: {formatted_duration}."
            )
            
            # Limpiar la sesión
            if 'active_round_id' in request.session: del request.session['active_round_id']
            
            if is_ajax:
                return JsonResponse({'status': 'success', 'message': 'Ronda finalizada correctamente.'})
            return redirect('operator_dashboard')
        else:
            if is_ajax:
                html = render_to_string('finish_virtual_round_modal_content.html', {'form': form, 'round': active_round}, request=request)
                return JsonResponse({'status': 'error', 'html': html})
    else:
        form = VirtualRoundCompletionForm(instance=active_round, installations_queryset=allowed_installations)

    if is_ajax:
        html = render_to_string('finish_virtual_round_modal_content.html', {'form': form, 'round': active_round}, request=request)
        return HttpResponse(html)

    return render(request, 'finish_virtual_round.html', {'form': form, 'round': active_round})

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

@login_required
@user_passes_test(is_supervisor)
@csrf_exempt
@transaction.atomic # Importante: Si uno falla, no se guarda ninguno
def api_save_shift_batch(request):
    if request.method == 'POST':
        try:
            payload = json.loads(request.body)
            changes = payload.get('changes', [])
            
            updated_count = 0
            deleted_count = 0

            for item in changes:
                operator_id = item.get('operator_id')
                date_str = item.get('date')
                shift_type_id = item.get('shift_type_id')
                company_ids = item.get('company_ids') # Puede ser None, [], o [1,2]

                if not operator_id or not date_str:
                    continue

                if shift_type_id:
                    # Crear o Actualizar
                    shift, created = OperatorShift.objects.update_or_create(
                        operator_id=operator_id,
                        date=date_str,
                        defaults={'shift_type_id': shift_type_id}
                    )
                    # Actualizar empresas si vienen en el payload
                    if company_ids is not None:
                        shift.monitored_companies.set(company_ids)
                    
                    updated_count += 1
                else:
                    # Eliminar si shift_type_id es vacío/null
                    OperatorShift.objects.filter(operator_id=operator_id, date=date_str).delete()
                    deleted_count += 1

            return JsonResponse({
                'status': 'success', 
                'message': f'Se guardaron {updated_count} asignaciones y se eliminaron {deleted_count}.'
            })

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
    return JsonResponse({'status': 'error'}, status=405)