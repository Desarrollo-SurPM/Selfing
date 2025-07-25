from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    
    # --- Admin ---
    path('dashboard/admin/', views.admin_dashboard, name='admin_dashboard'),
    path('email/approve/<int:email_id>/', views.approve_email, name='approve_email'),
    
    # Rutas para Gestionar Operadores
    path('dashboard/operators/', views.manage_operators, name='manage_operators'),
    path('dashboard/operators/add/', views.create_operator, name='create_operator'),
    path('dashboard/operators/edit/<int:user_id>/', views.edit_operator, name='edit_operator'),
    path('dashboard/operators/delete/<int:user_id>/', views.delete_operator, name='delete_operator'),

    # 👇 AÑADE ESTAS RUTAS PARA GESTIONAR EMPRESAS 👇
    path('dashboard/companies/', views.manage_companies, name='manage_companies'),
    path('dashboard/companies/add/', views.create_company, name='create_company'),
    path('dashboard/companies/edit/<int:company_id>/', views.edit_company, name='edit_company'),
    path('dashboard/companies/delete/<int:company_id>/', views.delete_company, name='delete_company'),
    # 👆 HASTA AQUÍ 👆

    # --- Operator ---
    path('dashboard/operator/', views.operator_dashboard, name='operator_dashboard'),
    path('checklist/', views.checklist_view, name='checklist'),
    path('update-log/', views.update_log_view, name='update_log'),
    path('email/new/', views.email_form_view, name='email_form'),
]