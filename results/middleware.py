from .models import School, Teacher

class SchoolMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        skip_paths = ['/ckeditor/', '/static/', '/media/']
        if any(request.path.startswith(p) for p in skip_paths):
            return self.get_response(request)

        request.school = None
        
        # 1. From session - set by school_admin_login, school_teacher_login, parent_login
        school_slug = request.session.get('school_slug')
        if school_slug:
            request.school = School.objects.filter(slug=school_slug).first()

        # 2. From logged in user - KEY FIX for Admin users
        if not request.school and request.user.is_authenticated:
            # Check if user is a Teacher
            try:
                teacher = Teacher.objects.get(user=request.user)
                request.school = teacher.school
            except Teacher.DoesNotExist:
                pass
            
            # Check if user is a School Admin - add this field to your User model
            if not request.school and hasattr(request.user, 'school') and request.user.school:
                request.school = request.user.school
        
        print(f"PATH: {request.path} | USER: {request.user} | SCHOOL: {request.school}")
        return self.get_response(request)