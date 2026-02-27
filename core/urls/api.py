from django.urls import path
from .. import views

urlpatterns = [
    # Shifts API
    path('api/shifts/update/', views.api_update_shift, name='api_update_shift'),
    path('api/shifts/batch-save/', views.api_save_shift_batch, name='api_save_shift_batch'),

    # Alarms & status
    path('api/check_alarms/', views.check_pending_alarms, name='check_pending_alarms'),

    # AJAX helpers
    path('ajax/get-updates/<int:company_id>/', views.get_updates_for_company, name='ajax_get_updates'),
    path('ajax/get-installations/<int:company_id>/', views.ajax_get_installations_for_company, name='ajax_get_installations_for_company'),
    path('ajax/get-service-status/', views.get_service_status, name='ajax_get_service_status'),
    path('ajax/shifts/', views.get_shifts_for_calendar, name='ajax_get_shifts_for_calendar'),
    path('ajax/check-first-round-started/', views.check_first_round_started, name='ajax_check_first_round_started'),

    # Weather
    path('api/weather/', views.get_weather_data, name='get_weather_data'),
    path('api/weather/cities/', views.get_multiple_cities_weather, name='get_multiple_cities_weather'),
]
