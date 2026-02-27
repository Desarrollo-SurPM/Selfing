from django.urls import path
from .. import views

urlpatterns = [
    path('gps/triage/', views.gps_triage_dashboard, name='gps_triage_dashboard'),
    path('gps/api/check-new/', views.check_new_gps_alerts, name='api_check_gps_alerts'),
    path('gps/admin/reports/', views.gps_admin_reports, name='gps_admin_reports'),
    path('gps/admin/export/', views.export_gps_excel, name='export_gps_excel'),
    path('gps/acknowledge/<int:incident_id>/', views.acknowledge_gps_incident, name='acknowledge_gps_incident'),
    path('gps/resolve/<int:incident_id>/', views.resolve_gps_incident, name='resolve_gps_incident'),
    path('gps/admin/settings/', views.manage_gps_settings, name='manage_gps_settings'),
]
