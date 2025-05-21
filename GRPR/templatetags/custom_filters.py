import json
from decimal import Decimal
from django import template

register = template.Library()

class DjangoJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)

@register.filter
def get_item(dictionary, key):
    """Custom filter to get an item from a dictionary by key."""
    return dictionary.get(key, None)

@register.filter
def to_json(value):
    return json.dumps(value, cls=DjangoJSONEncoder)