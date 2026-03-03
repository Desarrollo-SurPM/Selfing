from .auth import is_supervisor, home
from .admin_dashboard import admin_dashboard
from .admin_operators import manage_operators, create_operator, edit_operator, delete_operator
from .admin_companies import (
    manage_companies, create_company, edit_company, delete_company,
    manage_installations, create_installation, edit_installation, delete_installation
)
from .admin_checklist import (
    manage_checklist_items, create_checklist_item, edit_checklist_item,
    delete_checklist_item, update_checklist_order
)
from .admin_services import (
    manage_monitored_services, create_monitored_service,
    edit_monitored_service, delete_monitored_service
)
from .admin_shifts import (
    manage_shifts, api_update_shift, assign_shift, edit_assigned_shift, delete_assigned_shift,
    shift_matrix_view, manage_shift_types, create_shift_type, edit_shift_type, delete_shift_type,
    shift_calendar_view, get_shifts_for_calendar
)
from .admin_reports import view_turn_reports, gps_admin_reports, export_gps_excel
from .admin_contacts import (
    manage_emergency_contacts, create_emergency_contact,
    edit_emergency_contact, delete_emergency_contact
)
from .operator_dashboard import operator_dashboard, start_shift
from .operator_logbook import (
    my_logbook_view, edit_update_log, delete_update_log,
    full_logbook_view, current_logbook_view,
    dismiss_shift_note, create_shift_note_modal
)
from .operator_updates import update_log_view, review_and_send_novedades
from .checklist import checklist_index_view, checklist_phase_view, start_checklist_task, pause_checklist_task, finish_checklist_task
from .shift_reports import end_turn_preview, sign_turn_report
from .virtual_rounds import (
    start_virtual_round, virtual_round_view,
    start_round_installation, pause_round_installation,
    finish_round_installation, close_virtual_round
)
from .emergency import panic_button_view
from .gps import (
    gps_triage_dashboard, check_new_gps_alerts, acknowledge_gps_incident,
    resolve_gps_incident, manage_gps_settings
)
from .vehicles import (
    vehicle_security_dashboard, vehicle_activity_log, vehicle_route_detail,
    get_weather_data, get_multiple_cities_weather
)
from .api import (
    ajax_get_installations_for_company, get_updates_for_company,
    get_service_status, check_pending_alarms, check_first_round_started,
    api_save_shift_batch
)
