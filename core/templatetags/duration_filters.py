from django import template

register = template.Library()

@register.filter
def format_duration(seconds):
    """
    Convierte una duración en segundos al formato Hh Mm o Mm Ss.
    """
    if seconds is None:
        return "" # O "En curso", si lo prefieres

    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60

    if hours > 0:
        return f"{hours}h {minutes}m"
    elif minutes > 0:
        # Si quieres mostrar minutos y segundos:
        remaining_seconds = seconds % 60
        return f"{minutes}m {remaining_seconds}s"
    else:
        return f"{seconds}s"