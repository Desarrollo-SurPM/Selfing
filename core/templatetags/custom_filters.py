from django import template
from datetime import timedelta

register = template.Library()

@register.filter
def add_days(value, days):
    """Suma un número de días a una fecha."""
    if value:
        try:
            return value + timedelta(days=days)
        except (ValueError, TypeError):
            return value # Devuelve el valor original si hay error
    return value

@register.filter(name='get_item')
def get_item(dictionary, key):
    """
    Permite obtener el valor de un diccionario usando una llave.
    Uso en la plantilla: {{ mi_diccionario|get_item:mi_llave }}
    """
    return dictionary.get(key)