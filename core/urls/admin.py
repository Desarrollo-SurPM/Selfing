from django.urls import path
from .. import views

urlpatterns = [
    # Dashboard
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

    # Gestión de Checklist (Configuración)
    path('dashboard/checklist-items/', views.manage_checklist_items, name='manage_checklist_items'),
    path('dashboard/checklist-items/add/', views.create_checklist_item, name='create_checklist_item'),
    path('dashboard/checklist-items/edit/<int:item_id>/', views.edit_checklist_item, name='edit_checklist_item'),
    path('dashboard/checklist-items/delete/<int:item_id>/', views.delete_checklist_item, name='delete_checklist_item'),

    # Gestión de Servicios Monitoreados
    path('dashboard/monitored-services/', views.manage_monitored_services, name='manage_monitored_services'),
    path('dashboard/monitored-services/add/', views.create_monitored_service, name='create_monitored_service'),
    path('dashboard/monitored-services/edit/<int:service_id>/', views.edit_monitored_service, name='edit_monitored_service'),
    path('dashboard/monitored-services/delete/<int:service_id>/', views.delete_monitored_service, name='delete_monitored_service'),

    # Reportes
    path('dashboard/turn-reports/', views.view_turn_reports, name='view_turn_reports'),

    # Gestión de Turnos
    path('dashboard/shifts/matrix/', views.shift_matrix_view, name='shift_matrix_view'),
    path('dashboard/shift-types/', views.manage_shift_types, name='manage_shift_types'),
    path('dashboard/shift-types/add/', views.create_shift_type, name='create_shift_type'),
    path('dashboard/shift-types/edit/<int:type_id>/', views.edit_shift_type, name='edit_shift_type'),
    path('dashboard/shift-types/delete/<int:type_id>/', views.delete_shift_type, name='delete_shift_type'),
    path('dashboard/shifts/', views.manage_shifts, name='manage_shifts'),
    path('dashboard/shifts/assign/', views.assign_shift, name='assign_shift'),
    path('dashboard/shifts/edit/<int:shift_id>/', views.edit_assigned_shift, name='edit_assigned_shift'),
    path('dashboard/shifts/delete/<int:shift_id>/', views.delete_assigned_shift, name='delete_assigned_shift'),
    path('dashboard/shift-calendar/', views.shift_calendar_view, name='shift_calendar'),

    # Contactos de Emergencia
    path('dashboard/emergency-contacts/', views.manage_emergency_contacts, name='manage_emergency_contacts'),
    path('dashboard/emergency-contacts/add/', views.create_emergency_contact, name='create_emergency_contact'),
    path('dashboard/emergency-contacts/edit/<int:contact_id>/', views.edit_emergency_contact, name='edit_emergency_contact'),
    path('dashboard/emergency-contacts/delete/<int:contact_id>/', views.delete_emergency_contact, name='delete_emergency_contact'),

    # Revisión y envío de novedades
    path('dashboard/review-and-send/', views.review_and_send_novedades, name='review_and_send_novedades'),
]
