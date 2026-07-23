from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """
    Usage in template: {{ scores_dict|get_item:student.id }}
    Returns the score object for that student or None
    """
    if dictionary:
        return dictionary.get(key)
    return None