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