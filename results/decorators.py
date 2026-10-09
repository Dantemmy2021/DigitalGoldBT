from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse
from functools import wraps

def student_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, school_slug, *args, **kwargs):
        if not request.session.get('student_id'):
            messages.error(request, "Please login as a student first")
            return redirect('results:student_login', school_slug=school_slug)
        return view_func(request, school_slug, *args, **kwargs)
    return _wrapped_view

def staff_member_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, school_slug, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_staff:
            messages.error(request, "Staff login required")
            return redirect('admin:login')
        return view_func(request, school_slug, *args, **kwargs)
    return _wrapped_view