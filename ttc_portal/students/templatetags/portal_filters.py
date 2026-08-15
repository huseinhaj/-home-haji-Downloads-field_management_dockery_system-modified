from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Rudisha thamani ya dict kwa key — mfano: {{ dict|get_item:key }}."""
    try:
        return dictionary.get(key, 0)
    except AttributeError:
        return 0
