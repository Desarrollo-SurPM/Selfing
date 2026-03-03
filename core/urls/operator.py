from django.urls import path
from .. import views

urlpatterns = [
    # Dashboard y control de turno
    path('dashboard/operator/', views.operator_dashboard, name='operator_dashboard'),
    path('shift/start/', views.start_shift, name='start_shift'),
    path('turn/end/', views.end_turn_preview, name='end_turn_preview'),
    path('turn/sign/<int:report_id>/', views.sign_turn_report, name='sign_turn_report'),

    # Emergencia
    path('panic-button/', views.panic_button_view, name='panic_button'),

    # Novedades / Bitácora
    path('update-log/', views.update_log_view, name='update_log'),
    path('update-log/edit/<int:log_id>/', views.edit_update_log, name='edit_update_log'),
    path('update-log/delete/<int:log_id>/', views.delete_update_log, name='delete_update_log'),
    path('bitacora-24h/', views.full_logbook_view, name='full_logbook_view'),
    path('mi-bitacora/', views.my_logbook_view, name='my_logbook'),
    path('current_logbook/', views.current_logbook_view, name='current_logbook'),

    # Notas de turno
    path('notas-turno/descartar/<int:note_id>/', views.dismiss_shift_note, name='dismiss_shift_note'),
    path('notas-turno/crear/', views.create_shift_note_modal, name='create_shift_note_modal'),

    # Checklist interactivo
    path('checklist/', views.checklist_index_view, name='checklist_index'),
    path('checklist/phase/<str:phase>/', views.checklist_phase_view, name='checklist_phase'),
    path('checklist/update_order/', views.update_checklist_order, name='update_checklist_order'),
    path('checklist/start_task/<int:item_id>/', views.start_checklist_task, name='start_task'),
    path('checklist/pause_task/<int:item_id>/', views.pause_checklist_task, name='pause_task'),
    path('checklist/finish_task/<int:item_id>/', views.finish_checklist_task, name='finish_task'),

    # Rondas virtuales
    path('start_virtual_round/', views.start_virtual_round, name='start_virtual_round'),
    path('round/view/', views.virtual_round_view, name='virtual_round_view'),
    path('round/close/<int:round_id>/', views.close_virtual_round, name='close_virtual_round'),
    path('start_round_installation/<int:round_id>/<int:inst_id>/', views.start_round_installation, name='start_round_installation'),
    path('pause_round_installation/<int:round_id>/<int:inst_id>/', views.pause_round_installation, name='pause_round_installation'),
    path('finish_round_installation/<int:round_id>/<int:inst_id>/', views.finish_round_installation, name='finish_round_installation'),
]
