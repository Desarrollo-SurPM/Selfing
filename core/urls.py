from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),

    # --- Rutas de Administrador ---
    path('dashboard/admin/', views.admin_dashboard, name='admin_dashboard'),
    
    # Gestión de Operadores
    path('dashboard/operators/', views.manage_operators, name='manage_operators'),
    path('dashboard/operators/add/', views.create_operator, name='create_operator'),
    path('dashboard/operators/edit/<int:user_id>/', views.edit_operator, name='edit_operator'),
    path('dashboard/operators/delete/<int:user_id>/', views.delete_operator, name='delete_operator'),

    # Gestión de Empresas e Instalaciones
    path('dashboard/companies/', views.manage_companies, name='manage_companies'),
    path('dashboard/companies/add/', views.create_company, name='create_company'),
    path('dashboard/companies/edit/<int:company_id>/', views.edit_company, name='edit_company'),
    path('dashboard/companies/delete/<int:company_id>/', views.delete_company, name='delete_company'),
    path('dashboard/companies/<int:company_id>/installations/', views.manage_installations, name='manage_installations'),
    path('dashboard/installations/add/<int:company_id>/', views.create_installation, name='create_installation'),
    path('dashboard/installations/edit/<int:installation_id>/', views.edit_installation, name='edit_installation'),
    path('dashboard/installations/delete/<int:installation_id>/', views.delete_installation, name='delete_installation'),

    # Gestión de Checklist
    path('dashboard/checklist-items/', views.manage_checklist_items, name='manage_checklist_items'),
    path('dashboard/checklist-items/add/', views.create_checklist_item, name='create_checklist_item'),
    path('dashboard/checklist-items/edit/<int:item_id>/', views.edit_checklist_item, name='edit_checklist_item'),
    path('dashboard/checklist-items/delete/<int:item_id>/', views.delete_checklist_item, name='delete_checklist_item'),
    
    # Gestión de Monitoreo
    path('dashboard/monitored-services/', views.manage_monitored_services, name='manage_monitored_services'),
    path('dashboard/monitored-services/add/', views.create_monitored_service, name='create_monitored_service'),
    path('dashboard/monitored-services/edit/<int:service_id>/', views.edit_monitored_service, name='edit_monitored_service'),
    path('dashboard/monitored-services/delete/<int:service_id>/', views.delete_monitored_service, name='delete_monitored_service'),

    # Gestión de Reportes y Correos
    path('email/review/<int:email_id>/', views.review_and_approve_email, name='review_email'),
    path('dashboard/turn-reports/', views.view_turn_reports, name='view_turn_reports'),
    
    # --- Rutas de Gestión de Turnos (Fase 1) ---
    path('dashboard/shift-types/', views.manage_shift_types, name='manage_shift_types'),
    path('dashboard/shift-types/add/', views.create_shift_type, name='create_shift_type'),
    path('dashboard/shift-types/edit/<int:type_id>/', views.edit_shift_type, name='edit_shift_type'),
    path('dashboard/shift-types/delete/<int:type_id>/', views.delete_shift_type, name='delete_shift_type'),
    
    path('dashboard/shifts/', views.manage_shifts, name='manage_shifts'),
    path('dashboard/shifts/assign/', views.assign_shift, name='assign_shift'),
    path('dashboard/shifts/edit/<int:shift_id>/', views.edit_assigned_shift, name='edit_assigned_shift'),
    path('dashboard/shifts/delete/<int:shift_id>/', views.delete_assigned_shift, name='delete_assigned_shift'),

    # --- Rutas de Operador ---
    path('dashboard/operator/', views.operator_dashboard, name='operator_dashboard'),
    path('checklist/', views.checklist_view, name='checklist'),
    path('update-log/', views.update_log_view, name='update_log'),
    path('email/new/', views.email_form_view, name='email_form'),
    path('turn/end/', views.end_turn_preview, name='end_turn_preview'),
    path('turn/sign/<int:report_id>/', views.sign_turn_report, name='sign_turn_report'),

    path('shift/start/', views.start_shift, name='start_shift'),
    # Dentro de urlpatterns, junto a las otras rutas de gestión de turnos:
    path('dashboard/shift-calendar/', views.shift_calendar_view, name='shift_calendar'),
    # Rondas Virtuales
    path('round/start/', views.start_virtual_round, name='start_virtual_round'),
    path('round/finish/<int:round_id>/', views.finish_virtual_round, name='finish_virtual_round'),

    # --- Rutas AJAX ---
    path('ajax/get-updates/<int:company_id>/', views.get_updates_for_company, name='ajax_get_updates'),
    path('ajax/get-service-status/', views.get_service_status, name='ajax_get_service_status'),
    path('ajax/shifts/', views.get_shifts_for_calendar, name='ajax_get_shifts_for_calendar'),
]