from django.db import migrations

SERVICES_DATA = [
    {
        "name": "Conexión a Internet (Google)",
        "ip_address": "8.8.8.8",
        "is_active": True
    },
    {
        "name": "PC en Red de Ejemplo",
        "ip_address": "192.168.1.100",
        "is_active": False # Inactivo por defecto, como solicitaste
    }
]

def seed_data(apps, schema_editor):
    MonitoredService = apps.get_model('core', 'MonitoredService')
    for service_data in SERVICES_DATA:
        MonitoredService.objects.get_or_create(**service_data)

class Migration(migrations.Migration):
    dependencies = [
        # Asegúrate que el nombre de la migración anterior sea correcto
        ('core', '0001_initial'),
    ]
    operations = [
        migrations.RunPython(seed_data),
    ]