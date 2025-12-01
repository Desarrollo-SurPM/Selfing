from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.utils.html import format_html
from django.db.models import Count
from .models import (
    Company, Installation, OperatorProfile, ShiftType, OperatorShift,
    ChecklistItem, ChecklistLog, VirtualRoundLog, UpdateLog, Email, EmergencyContact,
    TurnReport, MonitoredService, ServiceStatusLog, TraceabilityLog, ShiftNote,
    Vehicle, VehiclePosition, VehicleAlert, VehicleRoute
)

# --- INLINES ---
class OperatorProfileInline(admin.StackedInline):
    model = OperatorProfile
    can_delete = False
    verbose_name_plural = 'Perfil de Operador'

class InstallationInline(admin.TabularInline):
    model = Installation
    extra = 0
    fields = ('name', 'address')
    show_change_link = True


# --- MODEL ADMINS ---

admin.site.unregister(User)
@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = (OperatorProfileInline,)

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'get_email_list', 'get_installation_count')
    search_fields = ('name', 'email')
    inlines = (InstallationInline,)

    @admin.display(description='Correos de Contacto')
    def get_email_list(self, obj):
        return ", ".join(obj.email.split(',')) if obj.email else 'N/A'

    @admin.display(description='Nº de Instalaciones')
    def get_installation_count(self, obj):
        return obj.installations.count()

@admin.register(Installation)
class InstallationAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'address')
    list_filter = ('company',)
    search_fields = ('name', 'company__name')

@admin.register(ShiftType)
class ShiftTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'start_time', 'end_time', 'duration_hours')
    search_fields = ('name',) # Requerido por OperatorShiftAdmin

@admin.register(OperatorShift)
class OperatorShiftAdmin(admin.ModelAdmin):
    list_display = ('date', 'operator', 'shift_type', 'actual_start_time', 'actual_end_time', 'is_active_now')
    list_filter = ('date', 'shift_type', 'operator')
    search_fields = ('operator__username', 'shift_type__name')
    date_hierarchy = 'date'
    autocomplete_fields = ('operator', 'shift_type')

    @admin.display(boolean=True, description='Turno Activo')
    def is_active_now(self, obj):
        return obj.actual_start_time is not None and obj.actual_end_time is None

# --- VISTAS CORREGIDAS PARA EDICIÓN EN LÍNEA ---

@admin.register(UpdateLog)
class UpdateLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'installation', 'message_snippet', 'is_sent', 'operator_shift') # <-- 'operator_shift' está en la lista
    list_filter = ('operator_shift__operator', 'installation__company', 'is_sent')
    search_fields = ('message', 'operator_shift__operator__username', 'installation__name')
    date_hierarchy = 'created_at'
    list_editable = ('operator_shift',) # <-- ¡CAMBIO CLAVE! Esto lo hace editable
    autocomplete_fields = ('operator_shift', 'installation') # Necesario para 'list_editable'

    @admin.display(description='Novedad')
    def message_snippet(self, obj):
        return obj.message[:50] + '...' if len(obj.message) > 50 else obj.message

@admin.register(ChecklistLog)
class ChecklistLogAdmin(admin.ModelAdmin):
    list_display = ('completed_at', 'get_item_description', 'observacion', 'operator_shift') # <-- 'operator_shift' está en la lista
    list_filter = ('operator_shift__operator', 'item__phase')
    search_fields = ('item__description', 'operator_shift__operator__username', 'observacion')
    date_hierarchy = 'completed_at'
    list_editable = ('operator_shift',) # <-- ¡CAMBIO CLAVE!
    autocomplete_fields = ('operator_shift', 'item')

    @admin.display(description='Tarea', ordering='item__description')
    def get_item_description(self, obj):
        return obj.item.description

@admin.register(VirtualRoundLog)
class VirtualRoundLogAdmin(admin.ModelAdmin):
    # La columna 'OPERADOR' se reemplaza por el campo editable 'operator_shift'
    list_display = ('start_time', 'end_time', 'get_duration_display', 'operator_shift') # <-- 'operator_shift' está en la lista
    list_filter = ('operator_shift__operator',)
    search_fields = ('operator_shift__operator__username',)
    date_hierarchy = 'start_time'
    list_editable = ('operator_shift',) # <-- ¡CAMBIO CLAVE!
    autocomplete_fields = ('operator_shift',) # Necesario para 'list_editable'

    @admin.display(description='Duración', ordering='duration_seconds')
    def get_duration_display(self, obj):
        return obj.get_duration_display()

# --- (El resto del archivo sigue igual) ---

@admin.register(ChecklistItem)
class ChecklistItemAdmin(admin.ModelAdmin):
    list_display = ('description', 'phase', 'order', 'alarm_trigger_delay')
    list_filter = ('phase',)
    search_fields = ('description',)
    list_editable = ('order',)
    ordering = ('phase', 'order')

@admin.register(EmergencyContact)
class EmergencyContactAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone_number', 'company', 'installation')
    list_filter = ('company',)
    search_fields = ('name', 'phone_number', 'company__name', 'installation__name')
    autocomplete_fields = ('company', 'installation')

@admin.register(TurnReport)
class TurnReportAdmin(admin.ModelAdmin):
    list_display = ('signed_at', 'operator', 'start_time', 'end_time', 'is_signed')
    list_filter = ('is_signed', 'operator')
    date_hierarchy = 'signed_at'

@admin.register(TraceabilityLog)
class TraceabilityLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'user', 'action')
    list_filter = ('user',)
    search_fields = ('user__username', 'action')
    date_hierarchy = 'timestamp'
    readonly_fields = ('timestamp', 'user', 'action')
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False

@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ('license_plate', 'driver_name', 'vehicle_type', 'company', 'is_active')
    list_filter = ('company', 'vehicle_type', 'is_active')
    search_fields = ('license_plate', 'driver_name')

@admin.register(VehiclePosition)
class VehiclePositionAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'vehicle', 'latitude', 'longitude', 'speed', 'is_connected')
    list_filter = ('is_connected', 'vehicle__company')
    search_fields = ('vehicle__license_plate',)
    date_hierarchy = 'timestamp'
    readonly_fields = ('timestamp', 'vehicle', 'latitude', 'longitude', 'speed', 'is_connected')

@admin.register(VehicleAlert)
class VehicleAlertAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'vehicle', 'alert_type', 'is_resolved')
    list_filter = ('alert_type', 'is_resolved', 'vehicle__company')
    search_fields = ('vehicle__license_plate', 'message')
    date_hierarchy = 'created_at'

@admin.register(VehicleRoute)
class VehicleRouteAdmin(admin.ModelAdmin):
    list_display = ('start_time', 'end_time', 'vehicle', 'total_distance', 'average_speed', 'max_speed')
    list_filter = ('vehicle__company',)
    search_fields = ('vehicle__license_plate',)
    date_hierarchy = 'start_time'

# Registrar los modelos restantes que no necesitan configuración especial
admin.site.register(Email)
admin.site.register(MonitoredService)
admin.site.register(ServiceStatusLog)
admin.site.register(ShiftNote)
admin.site.register(OperatorProfile)