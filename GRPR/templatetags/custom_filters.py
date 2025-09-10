import json
from decimal import Decimal
from django import template
from collections.abc import Mapping

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

# for new game setup workflow
@register.filter
def get_item(value, key):
    """
    Template helper to fetch dict items with arbitrary keys (e.g. '9:04').
    Returns [] if the key isn't present so you can safely iterate:
      {% for p in assignments|get_item:teetime %}
    Works with plain dicts and Mapping-like objects.
    """
    try:
        if isinstance(value, Mapping):
            return value.get(key, [])
        # Fallback for objects that support __getitem__
        return value[key]
    except Exception:
        return []


# for Gas Cup
@register.filter
def dict_get(d, key):
    """
    Safe dictionary lookup for templates.
    Accepts str/int key. Returns '' if not found.
    """
    if d is None:
        return ""
    # try raw
    if key in d:
        return d[key]
    # try coercions
    try:
        ikey = int(key)
        if ikey in d:
            return d[ikey]
    except Exception:
        pass
    # try str key
    skey = str(key)
    return d.get(skey, "")