from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Custom filter to get an item from a dictionary by key."""
    return dictionary.get(key, None)
