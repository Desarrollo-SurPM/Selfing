import imaplib
import email
import re
import html as py_html
from datetime import datetime
from django.utils import timezone
from django.conf import settings
from django.utils.html import strip_tags
from core.models import GPSIncident, Sector

class GPSAlertParser:
    def __init__(self):
        self.username = getattr(settings, 'GPS_EMAIL_HOST_USER')
        self.password = getattr(settings, 'GPS_EMAIL_HOST_PASSWORD')
        self.imap_server = getattr(settings, 'GPS_EMAIL_HOST')
        self.imap_port = getattr(settings, 'GPS_EMAIL_PORT', 993)
        
        self.regex_patterns = {
            'alert_type': r'detalles (?:sobre|de la) (.*?):',
            'license_plate': r'Unidad:\s*([A-Z0-9-]+)',
            'unit_id': r'SN:\s*([A-Z0-9]+)',
            'driver_name': r'Conductor\*?:\s*([^\n\r]+)',
            'location_text': r'Dirección de la calle:\s*([^\n\r]+)',
            'timestamp': r'Fecha y Hora:\s*(\d{2}/\d{2}/\d{4} - \d{2}:\d{2}:\d{2})',
            'latitude': r'Latitud:\s*(-?\d+\.\d+)',
            'longitude': r'Longitud:\s*(-?\d+\.\d+)'
        }

    def connect(self):
        try:
            mail = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            mail.login(self.username, self.password)
            return mail
        except Exception as e:
            print(f"Error de conexión IMAP: {e}")
            return None

    def is_point_in_polygon(self, lat, lon, polygon):
        """
        Algoritmo matemático de Ray-Casting.
        Verifica si un punto (lat, lon) está dentro de un polígono trazado.
        polygon = [[lat1, lon1], [lat2, lon2], ...]
        """
        if not polygon or len(polygon) < 3:
            return False

        x, y = float(lon), float(lat)
        inside = False
        n = len(polygon)
        
        p1x, p1y = float(polygon[0][1]), float(polygon[0][0])
        for i in range(n + 1):
            p2x, p2y = float(polygon[i % n][1]), float(polygon[i % n][0])
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xints = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xints:
                            inside = not inside
            p1x, p1y = p2x, p2y
            
        return inside

    def fallback_text_search(self, location_text):
        """Plan B: Búsqueda por texto si el vehículo no tiene coordenadas o está fuera de las geocercas."""
        if not location_text: return None
        location_lower = py_html.unescape(location_text).lower()
        
        keywords_map = {
            'Cabo Negro': ['cabo negro', 'laguna blanca', 'punta arenas', 'ruta 9', 'rio seco', 'río seco', 'chabunco'],
            'San Gregorio': ['san gregorio', 'villa o\'higgins', 'ruta ch-255', 'ruta 255', 'ch-255', 'kimiri aike'],
            'Posesion': ['posesion', 'posesión', 'faro posesión', 'bahía posesión'],
            'Cerro Sombrero': ['cerro sombrero', 'primavera', 'porvenir', 'tierra del fuego', 'cullen', 'bahía lomas']
        }

        for sector_name, keywords in keywords_map.items():
            if any(keyword in location_lower for keyword in keywords):
                return Sector.objects.filter(name__icontains=sector_name).first()
        return None

    def get_assigned_sector(self, lat, lon, location_text):
        """Paso 1: Matemática. Paso 2: Texto."""
        if lat and lon:
            try:
                plat = float(lat)
                plon = float(lon)
                # Buscamos en todos los sectores que tengan una geocerca configurada
                sectores_con_geocerca = Sector.objects.exclude(geofence_polygon__isnull=True)
                for sector in sectores_con_geocerca:
                    if self.is_point_in_polygon(plat, plon, sector.geofence_polygon):
                        return sector
            except Exception as e:
                print(f"Error evaluando coordenadas: {e}")

        # Si no hay coordenadas, o el vehículo está fuera de las geocercas, usamos el texto
        return self.fallback_text_search(location_text)

    def process_unread_emails(self):
        mail = self.connect()
        if not mail: return 0

        mail.select("inbox")
        status, messages = mail.search(None, "UNSEEN")
        if status != "OK" or not messages[0]:
            mail.logout()
            return 0

        incidentes_creados = 0
        for e_id in messages[0].split():
            res, msg_data = mail.fetch(e_id, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    
                    raw_html = ""
                    body_clean = ""
                    
                    for part in msg.walk():
                        content_type = part.get_content_type()
                        if content_type in ["text/plain", "text/html"]:
                            charset = part.get_content_charset() or 'utf-8'
                            payload = part.get_payload(decode=True)
                            try:
                                text = payload.decode(charset, errors='replace')
                            except LookupError:
                                text = payload.decode('utf-8', errors='replace')
                            
                            if content_type == "text/html":
                                raw_html += text
                                text = strip_tags(text)
                            
                            body_clean += text + "\n"

                    body_clean = re.sub(r'\n+', '\n', body_clean)

                    # 1. Extraer con Regex y SOLUCIONAR TILDES
                    data = {}
                    for key, pattern in self.regex_patterns.items():
                        match = re.search(pattern, body_clean, re.IGNORECASE)
                        if match:
                            extracted_value = match.group(1).strip()
                            data[key] = py_html.unescape(extracted_value)
                        else:
                            data[key] = None

                    if not data.get('license_plate') or not data.get('alert_type'):
                        continue

                    # 2. Link Mapa
                    maps_url = None
                    map_match = re.search(r'href="([^"]+)"[^>]*>Abrir en Goo', raw_html, re.IGNORECASE)
                    if map_match:
                        maps_url = map_match.group(1)
                    elif data.get('latitude') and data.get('longitude'):
                        maps_url = f"https://www.google.com/maps?q={data.get('latitude')},{data.get('longitude')}"

                    # 3. Parsear Fecha
                    try:
                        dt_obj = datetime.strptime(data.get('timestamp'), '%d/%m/%Y - %H:%M:%S')
                        incident_timestamp = timezone.make_aware(dt_obj)
                    except:
                        incident_timestamp = timezone.now()

                    # 4. ASIGNACIÓN MATEMÁTICA DE SECTOR
                    sector = self.get_assigned_sector(data.get('latitude'), data.get('longitude'), data.get('location_text'))

                    GPSIncident.objects.create(
                        alert_type=data.get('alert_type'),
                        unit_id=data.get('unit_id'),
                        license_plate=data.get('license_plate'),
                        driver_name=data.get('driver_name'),
                        location_text=data.get('location_text') or "Sin ubicación",
                        incident_timestamp=incident_timestamp,
                        sector_assigned=sector,
                        status='pending',
                        latitude=data.get('latitude'),
                        longitude=data.get('longitude'),
                        maps_url=maps_url
                    )
                    incidentes_creados += 1

        mail.logout()
        return incidentes_creados