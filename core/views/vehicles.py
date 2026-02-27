import json
from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.utils import timezone
from ..models import Vehicle, VehiclePosition, VehicleAlert, VehicleRoute
from .auth import is_supervisor


@login_required
@user_passes_test(is_supervisor)
def vehicle_security_dashboard(request):
    import requests as http_requests
    CIUDADES_CHILE = {
        'punta arenas': {'lat': -53.162, 'lon': -70.917},
        'puerto natales': {'lat': -51.723, 'lon': -72.497},
        'santiago': {'lat': -33.45, 'lon': -70.66},
        'valparaiso': {'lat': -33.045, 'lon': -71.619},
        'concepcion': {'lat': -36.826, 'lon': -73.050},
    }
    ciudad_buscada = request.GET.get('ciudad', 'punta arenas').lower()
    coordenadas = CIUDADES_CHILE.get(ciudad_buscada, CIUDADES_CHILE['punta arenas'])

    vehicles = Vehicle.objects.filter(is_active=True)
    vehicles_on_route = vehicles_stopped = vehicles_disconnected = 0

    vehicle_positions = []
    for vehicle in vehicles:
        latest_position = VehiclePosition.objects.filter(vehicle=vehicle).order_by('-timestamp').first()
        if latest_position:
            vehicle_positions.append({
                'vehicle': vehicle.license_plate,
                'lat': float(latest_position.latitude),
                'lng': float(latest_position.longitude),
                'speed': latest_position.speed,
                'connected': latest_position.is_connected,
                'driver': vehicle.driver_name
            })

    for pos in vehicle_positions:
        if not pos['connected']:
            vehicles_disconnected += 1
        elif pos['speed'] > 5:
            vehicles_on_route += 1
        else:
            vehicles_stopped += 1

    active_alerts = VehicleAlert.objects.filter(
        is_resolved=False, vehicle__is_active=True
    ).select_related('vehicle').order_by('-created_at')[:10]
    vehicle_alerts = [{
        'vehicle': a.vehicle.license_plate,
        'type': a.alert_type,
        'message': a.message,
        'time': a.created_at.strftime('%H:%M')
    } for a in active_alerts]

    recent_routes = VehicleRoute.objects.filter(
        vehicle__is_active=True,
        start_time__date=timezone.now().date()
    ).select_related('vehicle').order_by('-start_time')[:10]
    vehicle_reports = [{
        'vehicle': r.vehicle.license_plate,
        'driver': r.vehicle.driver_name,
        'time': f'{r.total_distance:.1f} km' if r.total_distance else 'N/A',
        'issue': 'Ruta completada' if r.end_time else 'En progreso'
    } for r in recent_routes]

    try:
        api_key = "tu_api_key_aqui"
        response = http_requests.get(
            f"http://api.openweathermap.org/data/2.5/weather?q=Punta Arenas,CL&appid={api_key}&units=metric&lang=es",
            timeout=5
        )
        if response.status_code == 200:
            weather_json = response.json()
            weather_data = {
                'temperature': round(weather_json['main']['temp']),
                'description': weather_json['weather'][0]['description'].capitalize(),
                'humidity': weather_json['main']['humidity'],
                'wind_speed': round(weather_json['wind']['speed'] * 3.6)
            }
        else:
            weather_data = {'temperature': 8, 'description': 'Viento fuerte', 'humidity': 75, 'wind_speed': 35}
    except Exception:
        weather_data = {'temperature': 8, 'description': 'Viento fuerte', 'humidity': 75, 'wind_speed': 35}

    stats = {'speed_violations': 3, 'stopped_time_avg': 45, 'longest_drive_time': 8, 'connection_issues': 2}

    vehicles_data = []
    for vehicle in vehicles:
        latest_position = VehiclePosition.objects.filter(vehicle=vehicle).order_by('-timestamp').first()
        if latest_position:
            vehicles_data.append({
                'id': vehicle.id,
                'name': vehicle.license_plate,
                'lat': float(latest_position.latitude),
                'lng': float(latest_position.longitude),
                'speed': latest_position.speed,
                'status': 'En ruta' if latest_position.speed > 5 else ('Offline' if not latest_position.is_connected else 'Detenido'),
                'driver': vehicle.driver_name,
                'weather': {'temp': 8, 'condition': 'Viento fuerte', 'icon': '💨'},
                'speedLimit': 50, 'fuel': 75, 'odometer': 45230, 'lastMaintenance': '15/11/2024',
                'model': f'{vehicle.get_vehicle_type_display()} {vehicle.created_at.year}',
                'engine': 'Encendido' if latest_position.speed > 0 else 'Apagado',
                'doors': 'Cerradas', 'battery': 95
            })

    context = {
        'waze_lat': coordenadas['lat'],
        'waze_lon': coordenadas['lon'],
        'ciudad_actual': ciudad_buscada.title(),
        'vehicles': vehicles,
        'vehicles_data': json.dumps(vehicles_data),
        'vehicle_positions': vehicle_positions,
        'vehicle_alerts': vehicle_alerts,
        'vehicle_reports': vehicle_reports,
        'weather_data': weather_data,
        'stats': stats,
        'total_vehicles': len(vehicle_positions),
        'vehicles_on_route': vehicles_on_route,
        'vehicles_stopped': vehicles_stopped,
        'vehicles_disconnected': vehicles_disconnected,
    }
    return render(request, 'vehicles/dashboard.html', context)


@login_required
@user_passes_test(is_supervisor)
def vehicle_activity_log(request):
    demo_activities = [
        {
            'id': 1, 'vehicle': 'ABC-123', 'driver': 'Juan Pérez',
            'start_time': '08:00', 'end_time': '16:30',
            'route': 'Santiago - Valparaíso', 'distance': '120 km',
            'avg_speed': '65 km/h', 'max_speed': '85 km/h',
            'stop_time': '45 min', 'weather': 'Soleado'
        },
        {
            'id': 2, 'vehicle': 'DEF-456', 'driver': 'María González',
            'start_time': '09:15', 'end_time': '17:45',
            'route': 'Santiago - Rancagua', 'distance': '87 km',
            'avg_speed': '58 km/h', 'max_speed': '75 km/h',
            'stop_time': '120 min', 'weather': 'Nublado'
        },
    ]
    return render(request, 'vehicles/activity_log.html', {'activities': demo_activities})


@login_required
@user_passes_test(is_supervisor)
def vehicle_route_detail(request, activity_id):
    demo_route_details = {
        1: {
            'vehicle': 'ABC-123', 'driver': 'Juan Pérez',
            'start_time': '08:00', 'end_time': '16:30', 'duration': '8h 30min',
            'route': 'Santiago - Valparaíso', 'distance': '120 km',
            'avg_speed': '65 km/h', 'max_speed': '85 km/h', 'stop_time': '45 min',
            'weather_start': 'Soleado, 18°C', 'weather_end': 'Parcialmente nublado, 22°C',
            'route_points': [{'lat': -33.4489, 'lng': -70.6693, 'time': '08:00', 'speed': 0}],
            'stops': [{'location': 'Estación Quilpué', 'duration': '15 min', 'time': '10:15'}],
            'alerts': []
        },
    }
    route_detail = demo_route_details.get(activity_id, demo_route_details[1])
    return render(request, 'vehicles/route_detail.html', {'route_detail': route_detail, 'activity_id': activity_id})


@login_required
@user_passes_test(is_supervisor)
def get_weather_data(request):
    import requests as http_requests
    lat = request.GET.get('lat', -33.4489)
    lon = request.GET.get('lon', -70.6693)
    api_key = 'af043322c5d5657c7b6c16a888ecd196'
    try:
        response = http_requests.get(
            f'https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units=metric&lang=es',
            timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            return JsonResponse({
                'temperature': round(data['main']['temp']),
                'description': data['weather'][0]['description'].title(),
                'humidity': data['main']['humidity'],
                'wind_speed': round(data['wind']['speed'] * 3.6),
                'icon': data['weather'][0]['icon']
            })
    except Exception:
        pass
    return JsonResponse({
        'temperature': 20, 'description': 'Datos no disponibles',
        'humidity': 60, 'wind_speed': 10, 'icon': '01d'
    })


@login_required
@user_passes_test(is_supervisor)
def get_multiple_cities_weather(request):
    return JsonResponse({})
