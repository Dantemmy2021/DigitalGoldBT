from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    if dictionary is None:
        return ''
    return dictionary.get(key, '')

@register.filter
def get_grade(school, total):
    if total in [None, '', 0]: 
        return ''
    try:
        total = float(total)
        grade_obj = school.grades.filter(min_score__lte=total, max_score__gte=total).first()
        return grade_obj.grade if grade_obj else ''
    except: 
        return ''

@register.filter
def get_remark(school, total):
    if total in [None, '', 0]: 
        return ''
    try:
        total = float(total)
        grade_obj = school.grades.filter(min_score__lte=total, max_score__gte=total).first()
        return grade_obj.remark if grade_obj else ''
    except: 
        return ''

@register.filter  # <-- ADD THIS ONE
def get_range(value):
    """Returns range(1, value+1) for looping in templates"""
    try:
        return range(1, int(value) + 1)
    except:
        return []