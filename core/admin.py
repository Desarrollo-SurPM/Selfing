from django.contrib import admin
from .models import Company, OperatorProfile, ChecklistItem, ChecklistLog, UpdateLog, Email, TraceabilityLog

admin.site.register(Company)
admin.site.register(OperatorProfile)
admin.site.register(ChecklistItem)
admin.site.register(ChecklistLog)
admin.site.register(UpdateLog)
admin.site.register(Email)
admin.site.register(TraceabilityLog)