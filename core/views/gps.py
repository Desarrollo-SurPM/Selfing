import json
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.contrib import messages
from django.utils import timezone
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.core.mail import send_mail, get_connection
from django.conf import settings
from ..models import GPSIncident, GPSNotificationSettings
from ..forms import GPSNotificationSettingsForm
from .auth import is_supervisor


@login_required
def gps_triage_dashboard(request):
    incidents = GPSIncident.objects.filter(
        status__in=['pending', 'in_progress']
    ).order_by('-incident_timestamp')
    return render(request, 'gps/triage_dashboard.html', {'incidents': incidents})


def check_new_gps_alerts(request):
    pending_count = GPSIncident.objects.filter(status='pending').count()
    latest_alert = GPSIncident.objects.filter(status='pending').order_by('-incident_timestamp').first()
    latest_info = {
        'type': latest_alert.alert_type,
        'plate': latest_alert.license_plate,
        'id': latest_alert.id
    } if latest_alert else None
    return JsonResponse({'pending_count': pending_count, 'latest_alert': latest_info})


@require_POST
def acknowledge_gps_incident(request, incident_id):
    try:
        incident = GPSIncident.objects.get(id=incident_id)
        incident.status = 'in_progress'
        incident.operator = request.user
        incident.taken_at = timezone.now()
        incident.save()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@require_POST
def resolve_gps_incident(request, incident_id):
    try:
        data = json.loads(request.body)
        incident = GPSIncident.objects.get(id=incident_id)
        incident.status = 'resolved'
        incident.who_answered = data.get('who_answered', 'No especificado')
        incident.operator_notes = data.get('operator_notes', '')
        incident.resolved_at = timezone.now()
        incident.save()
        enviar_correo_resolucion_gps(incident)
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


def enviar_correo_resolucion_gps(incident):
    subject = f"RESOLUCIÓN ALERTA GPS: {incident.alert_type} - Unidad {incident.license_plate}"
    context = {'incident': incident}
    html_message = render_to_string('emails/gps_resolution.html', context)
    plain_message = strip_tags(html_message)

    config, _ = GPSNotificationSettings.objects.get_or_create(id=1)
    destinatarios = config.get_instant_emails_list() if config.get_instant_emails_list() else ['soporte@selfing.cl']

    connection = get_connection(
        host=settings.EMAIL_HOST,
        port=settings.EMAIL_PORT,
        username=settings.GPS_EMAIL_HOST_USER,
        password=settings.GPS_EMAIL_HOST_PASSWORD,
        use_ssl=settings.EMAIL_USE_SSL,
        use_tls=settings.EMAIL_USE_TLS,
    )
    send_mail(
        subject=subject,
        message=plain_message,
        from_email=settings.GPS_EMAIL_HOST_USER,
        recipient_list=destinatarios,
        html_message=html_message,
        connection=connection,
        fail_silently=False,
    )


@login_required
@user_passes_test(is_supervisor)
def manage_gps_settings(request):
    config, _ = GPSNotificationSettings.objects.get_or_create(id=1)
    if request.method == 'POST':
        config.instant_emails = request.POST.get('instant_emails', '')
        config.monthly_emails = request.POST.get('monthly_emails', '')
        config.save()
        messages.success(request, "Configuración de correos GPS actualizada correctamente.")
        return redirect('admin_dashboard')
    return render(request, 'admin/gps/settings_form.html', {'config': config})
