from django.urls import path
from .. import views

urlpatterns = [
    path('dashboard/vehicle-security/', views.vehicle_security_dashboard, name='vehicle_security_dashboard'),
    path('dashboard/vehicle-activity/', views.vehicle_activity_log, name='vehicle_activity_log'),
    path('dashboard/vehicle-route/<int:activity_id>/', views.vehicle_route_detail, name='vehicle_route_detail'),
]
