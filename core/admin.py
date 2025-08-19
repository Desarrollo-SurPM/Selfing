from django.contrib import admin
from .models import Company, OperatorProfile, ChecklistItem, ChecklistLog, UpdateLog, Email, TraceabilityLog,  EmergencyContact

admin.site.register(Company)
admin.site.register(OperatorProfile)
admin.site.register(ChecklistItem)
admin.site.register(ChecklistLog)
admin.site.register(UpdateLog)
admin.site.register(Email)
admin.site.register(TraceabilityLog)
admin.site.register(EmergencyContact)