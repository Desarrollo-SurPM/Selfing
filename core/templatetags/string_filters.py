from django import template

register = template.Library()

@register.filter(name='split')
def split_string(value, arg):
    """
    Divide una cadena de texto por un delimitador.
    Uso: {{ some_string|split:"," }}
    """
    if value:
        return value.split(arg)
    return []