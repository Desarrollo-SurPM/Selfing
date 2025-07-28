import os
from django.core.management.base import BaseCommand
from core.models import ChecklistItem

# --- DATOS EXTRAÍDOS DEL DOCUMENTO WORD ---

CHECKLIST_DATA = {
    'INICIO': [
        "Informar vía WhatsApp inicio del turno.",
        "Chequear operativo suministro normal de energía eléctrica en sala de control y UPS. (Cada domingo AM prueba del generador por 15 min.)",
        "Chequear iluminación de sala de control.",
        "Chequear calefacción de sala de control.",
        "Chequear el mobiliario, baño e instalaciones conforme para el uso durante el turno.",
        "Asegurar conectividad de señal internet (Router CISCO encendido) y Fire Wall FORTIGATE (Siempre debe estar encendido).",
        "Puesta en marcha de equipos monitores y servidores (Si aplica).",
        "Realizar prueba de volumen de monitores.",
        "Chequear correcta operatividad y carga de celular de sala de control.",
        "Chequear armado alarmas, analíticas y bocinas RECASUR.",
        "Chequear armado alarmas, analíticas y bocinas ICV.",
        "Chequear armado alarmas, analíticas y bocinas AGUNSA.",
        "Revisión de correo y WEB MITTA.",
        "Revisión de todas las cámaras y mantener rondas 1 hora.",
        "Abrir libro de novedades.",
    ],
    'DURANTE': [
        "Se debe mantener observación permanente de cámaras de instalaciones a resguardo.",
        "Debe quedar registrada en libro de novedades alarma generada y reconocida.",
        "Se debe tomar fotografía instantánea en caso de cualquier duda o necesidad de registrar.",
        "Se debe realizar ronda virtual por todas las cámaras cada una hora como mínimo.",
        "Se debe revisar cada una hora WEB MITTA y actualizar correo electrónico ante llegada de ALERTA de alguna unidad vehicular.",
    ],
    'FIN': [
        "Enviar mail 08:30 informando al cliente las novedades del turno.",
        "Finalizar libro de novedades con toda la información exigida según formato y firma del operador saliente.",
        "Para entrega de turno discontinuos se deberá dejar cerrada la sesión Recasur, cerrar apagado video Wall y apagar servidor Selfing (Off Line). FORTINET no se debe accionar!!!",
        "Dejar en condiciones de orden y aseo el puesto de trabajo.",
        "Verificar calefacción según condiciones climáticas.",
        "Apagado de iluminación.",
        "Entregar celulares cargados.",
    ]
}


class Command(BaseCommand):
    help = 'Pobla la base de datos con los ítems del checklist desde el documento de operaciones.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('--- Iniciando carga de Checklist ---'))
        
        items_creados = 0
        items_existentes = 0

        for phase, descriptions in CHECKLIST_DATA.items():
            self.stdout.write(self.style.HTTP_INFO(f'Cargando ítems para la fase: {phase}'))
            for desc in descriptions:
                # get_or_create evita crear duplicados si el script se corre varias veces.
                # Busca un ítem con la descripción. Si no lo encuentra, lo crea.
                obj, created = ChecklistItem.objects.get_or_create(
                    description=desc.strip(),
                    defaults={'phase': phase}
                )
                
                if created:
                    self.stdout.write(self.style.SUCCESS(f'  [+] Creado: "{obj.description}"'))
                    items_creados += 1
                else:
                    self.stdout.write(self.style.WARNING(f'  [*] Ya existe: "{obj.description}"'))
                    items_existentes += 1
        
        self.stdout.write(self.style.SUCCESS('--- Carga de Checklist Finalizada ---'))
        self.stdout.write(f'Resumen: {items_creados} ítems nuevos creados, {items_existentes} ítems ya existían.')