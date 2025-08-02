from .views import get_active_shift

def shift_context(request):
    """
    Hace que el turno activo del operador esté disponible en todas las plantillas.
    """
    if request.user.is_authenticated and not request.user.is_staff:
        active_shift = get_active_shift(request.user)
        return {'global_active_shift': active_shift}
    return {}