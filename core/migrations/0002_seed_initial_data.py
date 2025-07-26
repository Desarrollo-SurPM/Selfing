from django.db import migrations

# Lista de tareas para el checklist
CHECKLIST_ITEMS = [
    "Chequear suministro normal de energía eléctrica y UPS.",
    "Chequear iluminación y calefacción de sala de control.",
    "Asegurar conectividad de internet (Router y Firewall).",
    "Realizar prueba de volumen de monitores.",
    "Chequear operatividad y carga de celular de sala de control.",
    "Realizar ronda virtual por todas las cámaras (recordatorio cada hora).",
    "Dejar en condiciones de orden y aseo el puesto de trabajo.",
]

# Datos de ejemplo para Empresas e Instalaciones
COMPANIES_DATA = {
    "RECASUR": ["Bodega Central", "Oficina Pto. Arenas"],
    "AGUNSA": ["Oficina Principal"],
    "ICV": ["Barrio Industrial Sitio 13"],
    "Oficina": ["Central de Monitoreo Selfing"]
}

def seed_data(apps, schema_editor):
    ChecklistItem = apps.get_model('core', 'ChecklistItem')
    Company = apps.get_model('core', 'Company')
    Installation = apps.get_model('core', 'Installation')

    # Poblar Checklist
    for item_desc in CHECKLIST_ITEMS:
        ChecklistItem.objects.get_or_create(description=item_desc)

    # Poblar Empresas e Instalaciones
    for company_name, installations in COMPANIES_DATA.items():
        company, created = Company.objects.get_or_create(name=company_name)
        for inst_name in installations:
            Installation.objects.get_or_create(company=company, name=inst_name)

class Migration(migrations.Migration):
    dependencies = [
        ('core', '0001_initial'),
    ]
    operations = [
        migrations.RunPython(seed_data),
    ]