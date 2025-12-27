import re
from datetime import datetime, time
from django.utils import timezone
from core.models import OperatorShift, Company, Installation, UpdateLog
from django.core.exceptions import ObjectDoesNotExist

# --- 1. CONFIGURACIÓN ---
TARGET_SHIFT_ID = 290  # ID del turno de Mario Sanchez

# --- 2. DATOS DEL REPORTE ---
raw_data = """
AGUNSA
13/12 08:33 Sale 01 femenina, reja de acceso cerrada con llave.
13/12 08:47 Ingresa 01 femenina, reja de acceso abierta.
13/12 08:50 Sale 01 femenina, reja de acceso cerrada con llave.
13/12 10:23 Ingresa Sr Juan Carlos Bacho, reja de acceso cerrada.
13/12 11:53 Sale Sr Juan Carlos Bacho, reja de acceso cerrada con llave.
13/12 12:37 Ingresa 01 masculino, reja de acceso abierta.
13/12 13:00 Sale 01 masculino, reja cerrada con llave (carga en camioneta 6 cajas desde el interior).
13/12 14:05 Ingresa 02 femeninas, reja de acceso abierta.
13/12 14:08 Sale 01 femenina, reja de acceso abierta.
13/12 14:10 Sale 01 femenina, reja de acceso cerrada con llave.
13/12 14:32 Ingresa 01 femenina y 01 masculino, reja de acceso abierta.
13/12 14:36 Sale 01 femenina y 01 masculino, reja de acceso cerrada con llave.
13/12 16:12 Reja de acceso con llave y oficinas cerradas.

Gregorio Energy
13/12 10:56 Se reestablece visualización de cámaras en locación.
13/12 11:04 Sale camioneta corporativa.
13/12 12:34 Se pierde visualización de cámaras en locación. (problemas en generador).
13/12 16:13 Se mantiene sin visualización en locación Bump Hill x 1.

ICV
Nutria
13/12 08:30 Portón de acceso cerrado, sin cuidador en campamento.
13/12 16:15 Portón de acceso cerrado, sin cuidador en campamento.
Sarmiento
13/12 08:30 Portón de acceso cerrado, sin cuidador en campamento.
13/12 16:15 Portón de acceso cerrado, sin cuidador en campamento.
Castillo
13/12 08:30 Portón de acceso cerrado, sin cuidador en campamento. Se encuentra pernoctando Sr Eduard Priedahita.
13/12 16:15 Portón de acceso cerrado, sin cuidador en campamento. Se encuentra pernoctando Sr Eduard Priedahita.

Chelech
Ferretería
13/12 09:00 Apertura de local, sin novedad.
13/12 16:15 Local abierto, sin novedad.
Gastromax Puq
13/12 09:00 Apertura de local, sin novedad.
13/12 13:00 Cierre de local, sin novedad
13/12 16:15 Local cerrado, sin novedad.
Patio constructor
13/12 09:00 Apertura de local, sin novedad.
13/12 16:15 Local abierto, sin novedad.
Bodega
13/12 09:00 Apertura de local, sin novedad.
13/12 16:15 Local abierto, sin novedad.
Expomuebles
13/12 09:30 Apertura de local, sin novedad.
13/12 16:15 Local abierto, sin novedad.
Gastromax Nat
13/12 10:00 Apertura de local, sin novedad.
13/12 16:15 Local abierto, sin novedad.
Multitienda
13/12 09:00 Apertura de local, sin novedad.
13/12 16:15 Local abierto, sin novedad.
Outdoor
13/12 09:00 Apertura de local, sin novedad.
13/12 16:15 Local abierto, sin novedad.

RECASUR
Centro de Distribución
13/12 08:30 Reja e instalaciones cerradas, sin novedad.
13/12 16:15 Reja de acceso e instalaciones cerradas, sin novedad.
Barranco Amarillo
13/12 08:30 Reja e instalaciones cerradas, sin novedad.
13/12 09:34 Abre e ingresa Sr Cesar Subiabre, en vehículo particular quien se estaciona en el ingreso.
13/12 10:11 Ingresan Sr Jaime Paredes y Sr Jorge Roseli en vehículo particular (previamente autorizado Sr Wladimir Ivelic), reja de acceso abierta.
13/12 10:12 Sale Sr Cesar Subiabre en vehículo particular, dejando reja de acceso cerrada sin candado.
13/12 12:17 Sale Sr Jaime Paredes y Sr Jorge Roseli en vehículo particular, se deja reja cerrada con candado (información es ratificada vía WhatsApp por Sr Wladimir Ivelic enviando una fotografía del cierre).
13/12 16:15 Reja de acceso e instalaciones cerradas, sin novedad.
"""

# --- 3. MAPEO EXACTO ---
INSTALLATION_MAP = {
    "AGUNSA_DEFAULT": "Centro",
    "Nutria": "ICV Campamento Nutria",
    "Sarmiento": "ICV Campamento Sarmiento",
    "Castillo": "ICV Campamento Cerro Castillo",
    "Ferretería": "Ferretería (NAT)",
    "Gastromax Puq": "Gastromax (PUQ)",
    "Patio constructor": "Patio Constructor (NAT)",
    "Bodega": "Bodega Central (NAT)",
    "Expomuebles": "Expo Muebles (NAT)",
    "Gastromax Nat": "Gastromax (NAT)",
    "Multitienda": "Multitienda (NAT)",
    "Outdoor": "Outdoor (NAT)",
    "Centro de Distribución": "Centro de Distribución",
    "Barranco Amarillo": "Barranco Amarillo",
    "GREGORIO_DEFAULT": "Pulling Gregorio Energy",
}

def run_import():
    print(f"--- Iniciando importación PRECISA al Turno ID: {TARGET_SHIFT_ID} ---")

    # 1. Obtener el Turno
    try:
        shift = OperatorShift.objects.get(pk=TARGET_SHIFT_ID)
        print(f"✅ Turno encontrado: {shift} | Operador: {shift.operator.username}")
    except ObjectDoesNotExist:
        print(f"❌ ERROR CRÍTICO: No existe el turno ID {TARGET_SHIFT_ID}")
        return

    current_company = None
    current_installation = None
    lines = raw_data.strip().split('\n')
    created_count = 0
    errors = []

    for line in lines:
        line = line.strip()
        if not line: continue

        # Detectar línea de Novedad (DD/MM HH:MM Mensaje)
        match = re.match(r'^(\d{2}/\d{2})\s+(\d{2}:\d{2})\s+(.*)', line)
        
        if match:
            # Procesar Novedad
            if not current_company:
                print(f"⚠️ Saltando línea (sin empresa): {line[:20]}...")
                continue
                
            time_str = match.group(2)
            message = match.group(3)

            # Determinar Instalación
            target_inst = current_installation
            
            # Si no hay instalación seleccionada (ej: bajo título AGUNSA)
            if not target_inst:
                comp_name_upper = current_company.name.upper()
                inst_name_search = None
                if "AGUNSA" in comp_name_upper:
                    inst_name_search = INSTALLATION_MAP["AGUNSA_DEFAULT"]
                elif "GREGORIO" in comp_name_upper:
                    inst_name_search = INSTALLATION_MAP["GREGORIO_DEFAULT"]

                if inst_name_search:
                    target_inst = Installation.objects.filter(company=current_company, name=inst_name_search).first()
                    if not target_inst:
                        target_inst = Installation.objects.filter(company=current_company, name__icontains=inst_name_search).first()

            if not target_inst:
                errors.append(f"Falta instalación para: '{line[:30]}...' en '{current_company.name}'")
                continue

            # Guardar en BD
            try:
                hour, minute = map(int, time_str.split(':'))
                manual_time_obj = time(hour, minute, 0)

                UpdateLog.objects.create(
                    operator_shift=shift,
                    installation=target_inst,
                    message=message,
                    manual_timestamp=manual_time_obj,
                    is_sent=False,
                    created_at=timezone.now()
                )
                created_count += 1
                print(f"   [+] {target_inst.name} ({time_str}) OK")
            except Exception as e:
                errors.append(f"Error DB: {e}")

        else:
            # Procesar Encabezado (Empresa o Instalación)
            # 1. Buscar Empresa
            comp = Company.objects.filter(name__icontains=line).first()
            if comp:
                current_company = comp
                current_installation = None
                print(f"\n🏢 EMPRESA: {comp.name}")
                continue

            # 2. Buscar Instalación (Mapeo Manual)
            mapped_name = INSTALLATION_MAP.get(line)
            if mapped_name and current_company:
                inst = Installation.objects.filter(company=current_company, name__icontains=mapped_name).first()
                if inst:
                    current_installation = inst
                    print(f"  📍 Instalación (Map): {inst.name}")
                    continue

            # 3. Buscar Instalación (Nombre Directo en Word)
            if current_company:
                inst = Installation.objects.filter(company=current_company, name__icontains=line).first()
                if inst:
                    current_installation = inst
                    print(f"  📍 Instalación (Directa): {inst.name}")
                    continue

    print(f"\n--- FIN ---")
    print(f"Novedades insertadas: {created_count}")
    if errors:
        print("ERRORES:")
        for e in errors: print(f"- {e}")

# Ejecutar la función
run_import()