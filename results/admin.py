from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User, Group
from django.utils.html import format_html
from django.urls import reverse
from.models import Subject, Student, Score

admin.site_header = "OKC School Portal Admin"
admin.site_title = "OKC Portal"
admin.site.index_title = "Welcome to OKC Administration"

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    # REMOVED admission_number because it doesn't exist in your Student model
    list_display = ('full_name', 'student_class', 'print_result_link')
    list_filter = ('student_class',)
    search_fields = ('full_name',) # removed admission_number
    list_per_page = 50

    def print_result_link(self, obj):
        url = reverse('results:admin_print_student', args=[obj.id])
        return format_html(
            '<a href="{}" target="_blank" style="background:#dc3545; color:white; padding:4px 8px; border-radius:4px; text-decoration:none;">🖨️ Print</a>',
            url
        )
    print_result_link.short_description = 'Print Slip'

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    # REMOVED subject_code because it doesn't exist in your Subject model
    list_display = ('name', 'student_class')
    list_filter = ('student_class',)
    search_fields = ('name',)
    filter_horizontal = ('teachers',) # makes it easy to assign multiple teachers

@admin.register(Score)
class ScoreAdmin(admin.ModelAdmin):
    list_display = ('student', 'subject', 'term', 'session', 'get_total', 'get_grade')
    list_filter = ('term', 'session', 'subject__student_class', 'subject')
    search_fields = ('student__full_name',) # removed admission_number
    readonly_fields = ('get_total', 'get_grade')
    list_per_page = 100

    def get_total(self, obj):
        return obj.ca1 + obj.ca2 + obj.project + obj.assignment + obj.exam
    get_total.short_description = 'Total'

    def get_grade(self, obj):
        total = self.get_total(obj)
        if total >= 70: return "A1"
        elif total >= 60: return "B2"
        elif total >= 50: return "B3"
        elif total >= 45: return "C4"
        elif total >= 40: return "C5"
        elif total >= 35: return "C6"
        elif total >= 30: return "D7"
        elif total >= 25: return "E8"
        else: return "F9"
    get_grade.short_description = 'Grade'

    def get_queryset(self, request): # Teachers only see their own subjects
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(subject__teachers=request.user)

    def formfield_for_foreignkey(self, db_field, request, **kwargs): # Limit dropdowns for teachers
        if db_field.name == "subject" and not request.user.is_superuser:
            kwargs["queryset"] = Subject.objects.filter(teachers=request.user)
        if db_field.name == "student" and not request.user.is_superuser:
            my_subjects = Subject.objects.filter(teachers=request.user)
            my_classes = my_subjects.values_list('student_class', flat=True).distinct()
            kwargs["queryset"] = Student.objects.filter(student_class__in=my_classes)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

class SubjectInline(admin.TabularInline): # For showing subjects inside User
    model = Subject.teachers.through
    extra = 1
    verbose_name = "Subject"
    verbose_name_plural = "Assigned Subjects"

class TeacherAdmin(UserAdmin):
    inlines = [SubjectInline]
    list_display = ('username', 'first_name', 'last_name', 'is_staff')
    list_filter = ('is_staff', 'is_superuser', 'groups')

# Unregister default and register custom
admin.site.unregister(User)
admin.site.unregister(Group)
admin.site.register(User, TeacherAdmin)