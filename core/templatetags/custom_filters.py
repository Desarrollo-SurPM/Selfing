from django import template

register = template.Library()

@register.filter(name='get_item')
def get_item(dictionary, key):
    """
    Permite obtener el valor de un diccionario usando una llave.
    Uso en la plantilla: {{ mi_diccionario|get_item:mi_llave }}
    """
    return dictionary.get(key)