# selfing/core/context_processors.py

from datetime import timedelta
from .models import VirtualRoundLog
from .views._helpers import get_active_shift

def shift_context(request):
    """
    Procesador de contexto unificado que hace que el turno activo y la
    hora de la próxima ronda estén disponibles globalmente en todas las plantillas.
    """
    # Si el usuario no está logueado o es un administrador, no hacemos nada.
    if not request.user.is_authenticated or request.user.is_staff:
        return {}
    
    # 1. Obtenemos el turno activo usando tu función existente.
    active_shift = get_active_shift(request.user)
    
    # Creamos el diccionario de contexto inicial.
    context = {'global_active_shift': active_shift}

    # 2. Si hay un turno activo e iniciado, calculamos la próxima ronda.
    if active_shift and active_shift.actual_start_time:
        FIRST_ROUND_DELAY = timedelta(minutes=30)
        ROUND_INTERVAL = timedelta(hours=1)

        last_round = VirtualRoundLog.objects.filter(
            operator_shift=active_shift
        ).order_by('-start_time').first()

        if last_round:
            next_round_due_time = last_round.start_time + ROUND_INTERVAL
        else:
            next_round_due_time = active_shift.actual_start_time + FIRST_ROUND_DELAY

        context['global_next_round_due_time_iso'] = next_round_due_time.isoformat()

    return context