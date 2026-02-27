import os
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.utils import timezone
from django.template.loader import render_to_string
from django.db import transaction
from django.core.mail import EmailMultiAlternatives
from ..models import Company, Installation, UpdateLog, OperatorShift, TraceabilityLog
from ..forms import UpdateLogForm, AdminUpdateLogForm
from ._helpers import get_active_shift, calculate_log_datetime
from .auth import is_supervisor


@login_required
def update_log_view(request):
    active_shift = get_active_shift(request.user)
    if not active_shift or not active_shift.actual_start_time:
        messages.error(request, "Debes iniciar un turno activo para registrar novedades.")
        return redirect('operator_dashboard')

    if request.method == 'POST':
        form = UpdateLogForm(request.POST, request.FILES)
        if form.is_valid():
            new_log = form.save(commit=False)
            new_log.operator_shift = active_shift
            if active_shift.monitored_companies.exists():
                company = new_log.installation.company
                if not active_shift.monitored_companies.filter(id=company.id).exists():
                    messages.error(request, "No tienes permiso para registrar novedades en esta empresa.")
                    return redirect('update_log')
            new_log.save()
            messages.success(request, 'Novedad registrada con éxito en la bitácora.')
            return redirect('update_log')
        else:
            messages.error(request, 'Hubo un error al guardar la novedad.')

    form = UpdateLogForm()
    companies_qs = active_shift.monitored_companies.all() if active_shift.monitored_companies.exists() else Company.objects.all()
    companies_with_installations = companies_qs.prefetch_related('installations')

    return render(request, 'operator/update_log/create.html', {'form': form, 'companies': companies_with_installations})


@login_required
@user_passes_test(lambda u: u.is_superuser)
def review_and_send_novedades(request):
    from datetime import time, timedelta
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

    if not cycle_shifts_qs.exists():
        messages.info(request, "Aún no ha finalizado un ciclo de turnos para generar un reporte.")
        return render(request, 'operator/review_send.html', {
            'companies': None,
            'add_novedad_form': AdminUpdateLogForm(cycle_shifts=cycle_shifts_qs)
        })

    next_shift_after_cycle = OperatorShift.objects.filter(actual_start_time__gte=end_of_cycle).first()
    if next_shift_after_cycle and next_shift_after_cycle.actual_end_time is not None:
        messages.info(request, "El periodo para enviar el reporte del ciclo anterior ha finalizado.")
        return render(request, 'operator/review_send.html', {
            'companies': None,
            'add_novedad_form': AdminUpdateLogForm(cycle_shifts=OperatorShift.objects.none())
        })

    form_to_render = None

    if request.method == 'POST':
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

                company_id_redirect = request.POST.get('company_id_for_redirect', '')
                if company_id_redirect:
                    return redirect(f"{request.path}?company_id={company_id_redirect}")
                return redirect('review_and_send_novedades')
            else:
                messages.error(request, 'Error al agregar la novedad.')
                form_to_render = form

        elif 'confirm_send' in request.POST:
            company_id_form = request.POST.get('company_id')
            company = get_object_or_404(Company, id=company_id_form)
            selected_ids = request.POST.getlist('updates_to_send')
            observations = request.POST.get('observations', '')

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

            updates_qs = UpdateLog.objects.filter(id__in=selected_ids).select_related(
                'operator_shift__shift_type', 'installation', 'operator_shift'
            )
            updates_list = list(updates_qs)
            updates_list.sort(key=lambda x: (x.installation.name, calculate_log_datetime(x)))

            email_string = company.email or ""
            recipient_list = [email.strip() for email in email_string.split(',') if email.strip()]

            if recipient_list:
                try:
                    protocol = 'https' if request.is_secure() else 'http'
                    domain = request.get_host()
                    base_url = f"{protocol}://{domain}"

                    email_context = {
                        'company': company,
                        'updates': updates_list,
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
                    TraceabilityLog.objects.create(
                        user=request.user,
                        action=f"Envió correo a {company.name} ({count_imgs} imgs)."
                    )
                    messages.success(request, f"Correo enviado a {company.name}.")
                except Exception as e:
                    messages.error(request, f"Error al enviar: {e}")
            else:
                messages.warning(request, f"{company.name} no tiene correo.")

            return redirect('review_and_send_novedades')

    if form_to_render is None:
        form_to_render = AdminUpdateLogForm(cycle_shifts=cycle_shifts_qs)

    company_id = request.GET.get('company_id')
    selected_company = None
    novedades_pendientes = None

    base_qs = UpdateLog.objects.filter(
        is_sent=False,
        operator_shift__in=cycle_shifts_qs
    ).select_related('installation__company', 'operator_shift__shift_type', 'operator_shift')

    company_ids = base_qs.values_list('installation__company_id', flat=True).distinct()
    companies_with_pending_updates = Company.objects.filter(id__in=company_ids).order_by('name')

    if company_id:
        try:
            selected_company = companies_with_pending_updates.get(id=int(company_id))
            raw_updates = list(base_qs.filter(installation__company=selected_company))
            raw_updates.sort(key=lambda x: (x.installation.name, calculate_log_datetime(x)))
            novedades_pendientes = raw_updates
        except (Company.DoesNotExist, ValueError):
            selected_company = None

    context = {
        'companies': companies_with_pending_updates,
        'selected_company': selected_company,
        'novedades_pendientes': novedades_pendientes,
        'cycle_end': end_of_cycle,
        'start_of_cycle': start_of_cycle,
        'add_novedad_form': form_to_render,
    }
    return render(request, 'operator/review_send.html', context)
