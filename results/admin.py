import requests
from django import forms
from django.contrib import admin, messages
from django.db.models import Q
from django.shortcuts import render
from django.urls import reverse
from django.utils.html import format_html
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.http import HttpResponseRedirect

from.models import (
    School, StudentClass, Subject, Student, Teacher, ScratchCard, StudentScore,
    AssessmentComponent, GradeScale, StudentNote, CATest, CATestQuestion, CATestResult, Attendance,
    Test, Question, StudentTestSession, StudentAnswer, Gallery, TeacherNote, Staff, StaffAttendance, News,
    StudentSubject, WhyChooseUsCard, AdmissionApplication, LessonPlan, Psychomotor,
)
from.views import send_email_to_student_parents

# ===== WHATSAPP CONFIG =====
WHATSAPP_TOKEN = 'PASTE_YOUR_TOKEN_HERE'
WHATSAPP_PHONE_ID = 'PASTE_YOUR_PHONE_ID_HERE'
WHATSAPP_URL = f"https://graph.facebook.com/v20.0/{WHATSAPP_PHONE_ID}/messages"

def send_whatsapp_message(phone_number, message):
    if not phone_number:
        return {"error": "No number"}
    if phone_number.startswith('0'):
        phone_number = '234' + phone_number[1:]
    if phone_number.startswith('+'):
        phone_number = phone_number[1:]
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": phone_number, "type": "text", "text": {"body": message}}
    try:
        response = requests.post(WHATSAPP_URL, headers=headers, json=data, timeout=10)
        return response.json()
    except Exception as e:
        print(f"WhatsApp Error: {e}")
        return {"error": str(e)}

TERM_CHOICES = [('First Term', 'First Term'), ('Second Term', 'Second Term'), ('Third Term', 'Third Term')]

class CsvImportForm(forms.Form):
    csv_file = forms.FileField(label='Select CSV file with questions')

class StaffAttendanceUploadForm(forms.Form):
    school = forms.ModelChoiceField(queryset=School.objects.all(), required=False)
    term = forms.ChoiceField(choices=TERM_CHOICES)
    attendance_file = forms.FileField(help_text="Upload.csv from ZKteco. Headers: User ID,Date,Time,Time_Out")

class PromoteStudentForm(forms.Form):
    _selected_action = forms.CharField(widget=forms.MultipleHiddenInput)
    new_class = forms.ModelChoiceField(queryset=StudentClass.objects.none(), label="Promote selected students to class")

class SchoolAdminMixin:
    def _get_school(self, request):
        # Try session first (for both superuser and normal)
        school_slug = request.session.get('school_slug')
        if school_slug:
            s = School.objects.filter(slug=school_slug).first()
            if s:
                return s

        if request.user.is_superuser:
            if School.objects.count() == 1:
                return School.objects.first()
            return None

        if hasattr(request.user, 'teacher') and hasattr(request.user.teacher, 'school'):
            return request.user.teacher.school

        try:
            staff = Staff.objects.get(user=request.user)
            return staff.school
        except:
            pass

        if School.objects.count() == 1:
            return School.objects.first()
        return None

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        school = self._get_school(request)
        if not school:
            return qs.none()
        model = self.model
        if model == School:
            return qs.filter(id=school.id)
        elif model == Student:
            return qs.filter(Q(school=school) | Q(student_class__school=school))
        elif model in [StudentScore, Attendance, StudentTestSession]:
            return qs.filter(student__student_class__school=school)
        elif model == StudentAnswer:
            return qs.filter(session__student__student_class__school=school)
        elif model == StudentNote:
            return qs.filter(student_class__school=school)
        elif model == TeacherNote:
            return qs.filter(school=school)
        elif model == StudentSubject:
            return qs.filter(student__student_class__school=school)
        elif hasattr(model, 'school'):
            return qs.filter(school=school)
        return qs

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if request.user.is_superuser:
            return super().formfield_for_foreignkey(db_field, request, **kwargs)
        school = self._get_school(request)
        if not school:
            return super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == "student":
            kwargs["queryset"] = Student.objects.filter(student_class__school=school)
        elif db_field.name == "subject":
            kwargs["queryset"] = Subject.objects.filter(school=school)
        elif db_field.name == "teacher":
            kwargs["queryset"] = Teacher.objects.filter(school=school)
        elif db_field.name == "student_class":
            kwargs["queryset"] = StudentClass.objects.filter(school=school)
        elif db_field.name == "school":
            kwargs["queryset"] = School.objects.filter(id=school.id)
            kwargs["initial"] = school
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

class QuestionInline(admin.TabularInline):
    model = Question
    extra = 1

@admin.register(School)
class SchoolAdmin(SchoolAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'slug', 'subdomain', 'current_session', 'current_term', 'principal_name', 'signature_preview', 'admission_form_fee']
    search_fields = ['name', 'slug', 'subdomain']
    prepopulated_fields = {'slug': ('name',)}
    fieldsets = (
        ('Basic Info', {'fields': ('name', 'slug', 'subdomain', 'logo', 'hero_image', 'motto', 'address', 'phone', 'email', 'map_embed')}),
        ('Branding', {'fields': ('primary_color', 'secondary_color')}),
        ('Academic Settings', {'fields': ('current_session', 'current_term', 'locked_terms', 'next_term_resumption_date')}),
        ('Principal Details - FOR RESULT', {'fields': ('principal_name', 'principal_signature')}),
        ('ADMISSION SAAS - PAYSTACK', {'fields': ('admission_form_fee', 'paystack_public_key', 'paystack_secret_key', 'admission_bank_account')}),
        ('Security', {'fields': ('allowed_ips',)}),
    )
    def signature_preview(self, obj):
        if obj.principal_signature:
            return format_html('<img src="{}" style="height: 80px;" />', obj.principal_signature.url)
        return "No signature uploaded"
    signature_preview.short_description = "Signature"
    def has_module_permission(self, request): return request.user.is_superuser
    def has_view_permission(self, request, obj=None): return request.user.is_superuser
    def has_add_permission(self, request): return request.user.is_superuser
    def has_change_permission(self, request, obj=None): return request.user.is_superuser
    def has_delete_permission(self, request, obj=None): return request.user.is_superuser

@admin.register(StudentClass)
class StudentClassAdmin(SchoolAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'arm', 'school', 'class_teacher', 'student_count', 'view_broadsheet']
    search_fields = ['name', 'arm', 'school__name']
    list_filter = ['school']
    list_editable = ['class_teacher']
    def student_count(self, obj):
        return obj.students.count()
    def view_broadsheet(self, obj):
        url = reverse('results:admin_broadsheet', args=[obj.school.slug, obj.id])
        return format_html('<a class="button" style="background:#004080; color:white; padding:5px 10px; border-radius:3px;" href="{}" target="_blank">📊 View Broadsheet</a>', url)
    def save_model(self, request, obj, form, change):
        if not obj.school_id:
            obj.school = self._get_school(request) or School.objects.first()
        super().save_model(request, obj, form, change)

class TeacherForm(forms.ModelForm):
    username = forms.CharField(required=False, help_text="e.g: john.ecwa - will auto-create login")
    password = forms.CharField(required=False, widget=forms.PasswordInput, initial="teacher1234")
    class Meta:
        model = Teacher
        fields = '__all__'

@admin.register(Teacher)
class TeacherAdmin(SchoolAdminMixin, admin.ModelAdmin):
    form = TeacherForm
    list_display = ('user', 'school', 'full_name', 'phone', 'signature_preview', 'passport_preview')
    list_filter = ('school',)
    filter_horizontal = ('subjects', 'classes')
    search_fields = ('user__username', 'full_name', 'phone')

    def signature_preview(self, obj):
        if obj.signature:
            return format_html('<img src="{}" style="height: 40px;" />', obj.signature.url)
        return "No signature"
    signature_preview.short_description = "Signature"

    def passport_preview(self, obj):
        if obj.passport:
            return format_html('<img src="{}" style="height: 40px; width:40px; object-fit:cover; border-radius:4px;" />', obj.passport.url)
        return "No passport"
    passport_preview.short_description = "Passport"

    def get_fieldsets(self, request, obj=None):
        if request.user.is_superuser:
            return [('Account', {'fields': ('user', 'school')}), ('Personal Info', {'fields': ('full_name', 'phone', 'signature', 'passport')}), ('Access', {'fields': ('subjects', 'classes')}),]
        else:
            return [('Create Teacher', {'fields': ('username', 'password', 'full_name', 'phone', 'signature', 'passport')}), ('Access', {'fields': ('subjects', 'classes')}),]

    def save_model(self, request, obj, form, change):
        if not obj.school_id:
            obj.school = self._get_school(request) or School.objects.first()
        if not obj.user_id:
            username = form.cleaned_data.get('username')
            if username:
                base = username
                counter = 1
                while User.objects.filter(username=username).exists():
                    username = f"{base}{counter}"
                    counter += 1
                password = form.cleaned_data.get('password') or 'teacher1234'
                user = User.objects.create_user(username=username, password=password)
                obj.user = user
        super().save_model(request, obj, form, change)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        school = self._get_school(request)
        if school and db_field.name == "school":
            kwargs["queryset"] = School.objects.filter(id=school.id)
            kwargs["initial"] = school
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        school = self._get_school(request)
        if school:
            if db_field.name == "subjects":
                kwargs["queryset"] = Subject.objects.filter(school=school)
            if db_field.name == "classes":
                kwargs["queryset"] = StudentClass.objects.filter(school=school)
        return super().formfield_for_manytomany(db_field, request, **kwargs)

@admin.register(Student)
class StudentAdmin(SchoolAdminMixin, admin.ModelAdmin):
    list_display = ('admission_no', 'full_name', 'student_class', 'parent_name', 'parent_email', 'parent_phone', 'view_transcript_btn', 'id_card_btn')
    list_filter = ('student_class',)
    search_fields = ('admission_no', 'full_name', 'parent_name', 'parent_phone', 'parent_email')
    list_editable = ('parent_email',)
    readonly_fields = ('view_transcript_btn',)
    actions = ['send_fee_reminder_action', 'promote_students_action', 'print_id_cards_action']
    autocomplete_fields = ['student_class']

    def view_transcript_btn(self, obj):
        if obj.id and obj.student_class and obj.student_class.school:
            url = reverse('student_transcript', args=[obj.student_class.school.slug, obj.id])
            return format_html(
                '<a href="{}" target="_blank" style="background:{}; color:white; padding:10px 18px; border-radius:6px; text-decoration:none; font-weight:bold; display:inline-block; min-width:130px; text-align:center; white-space:nowrap;">📄 Transcript</a>',
                url, obj.student_class.school.primary_color or '#004080'
            )
        return "Save first"
    view_transcript_btn.short_description = "Transcript"

    def id_card_btn(self, obj):
        if obj.student_class and obj.student_class.school:
            url = reverse('print_id_cards', args=[obj.student_class.school.slug]) + f"?student_id={obj.id}"
            return format_html(
                '<a href="{}" target="_blank" style="background:#28a745; color:white; padding:10px 18px; border-radius:6px; text-decoration:none; font-weight:bold; display:inline-block; min-width:100px; text-align:center; white-space:nowrap;">🪪 ID Card</a>',
                url
            )
        return "-"
    id_card_btn.short_description = "ID Card"

    @admin.action(description='🪪 Print ID Cards for Selected')
    def print_id_cards_action(self, request, queryset):
        first = queryset.first()
        if not first or not first.student_class or not first.student_class.school:
            self.message_user(request, "Cannot determine school", messages.ERROR)
            return
        school_slug = first.student_class.school.slug
        ids = ",".join([str(s.id) for s in queryset])
        url = reverse('print_id_cards', args=[school_slug]) + f"?ids={ids}"
        return HttpResponseRedirect(url)

    @admin.action(description='📧 Send Fee Reminder')
    def send_fee_reminder_action(self, request, queryset):
        count = 0
        for student in queryset:
            if student.parent_email and student.student_class:
                send_email_to_student_parents(student, f'School Fees Reminder - {student.full_name}', f'Dear {student.parent_name},\n\nReminder for {student.full_name}.\n\nThank you.\n{student.student_class.school.name} Management')
                count += 1
        self.message_user(request, f'Sent {count} fee reminder emails', messages.SUCCESS)

    @admin.action(description='🎓 Promote Selected')
    def promote_students_action(self, request, queryset):
        school = self._get_school(request) or School.objects.first()
        if 'apply' in request.POST:
            form = PromoteStudentForm(request.POST)
            form.fields['new_class'].queryset = StudentClass.objects.filter(school=school) if school else StudentClass.objects.all()
            if form.is_valid():
                new_class = form.cleaned_data['new_class']
                for student in queryset:
                    if student.student_class and student.student_class.school == new_class.school:
                        student.student_class = new_class
                        student.save()
                self.message_user(request, f"Promoted {queryset.count()} students to {new_class}", messages.SUCCESS)
                return
        else:
            form = PromoteStudentForm(initial={'_selected_action': request.POST.getlist('_selected_action')})
            form.fields['new_class'].queryset = StudentClass.objects.filter(school=school) if school else StudentClass.objects.all()
        return render(request, 'admin/promote_students.html', {'students': queryset, 'form': form, 'title': f'Promote {queryset.count()} Students'})

@admin.register(Subject)
class SubjectAdmin(SchoolAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'code')
    search_fields = ('name', 'code')
    list_per_page = 20
    def save_model(self, request, obj, form, change):
        if not obj.school_id:
            obj.school = self._get_school(request) or School.objects.first()
        super().save_model(request, obj, form, change)

@admin.register(StudentSubject)
class StudentSubjectAdmin(SchoolAdminMixin, admin.ModelAdmin):
    list_display = ('student', 'subject', 'student_class')
    list_filter = ('student_class', 'subject')
    search_fields = ('student__admission_no', 'student__full_name')
    autocomplete_fields = ['student', 'subject']

@admin.register(AssessmentComponent)
class AssessmentComponentAdmin(SchoolAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'max_score', 'order', 'school')

@admin.register(GradeScale)
class GradeScaleAdmin(SchoolAdminMixin, admin.ModelAdmin):
    list_display = ('school', 'grade', 'min_score', 'max_score', 'remark')

@admin.register(StudentScore)
class StudentScoreAdmin(SchoolAdminMixin, admin.ModelAdmin):
    list_display = ('student', 'subject', 'component', 'term', 'session', 'score')
    list_filter = ('term', 'session', 'subject')

@admin.register(ScratchCard)
class ScratchCardAdmin(SchoolAdminMixin, admin.ModelAdmin):
    list_display = ('pin', 'school', 'amount', 'used', 'used_by_student', 'date_used')
    list_filter = ('used',)

@admin.register(Staff)
class StaffAdmin(SchoolAdminMixin, admin.ModelAdmin):
    list_display = ['full_name', 'staff_id', 'device_staff_id', 'school', 'designation']

@admin.register(StaffAttendance)
class StaffAttendanceAdmin(SchoolAdminMixin, admin.ModelAdmin):
    list_display = ['staff', 'date', 'time_in', 'time_out', 'status', 'school', 'term']
    list_filter = ['status', 'date', 'term']

@admin.register(Test)
class TestAdmin(SchoolAdminMixin, admin.ModelAdmin):
    list_display = ['title', 'school', 'test_class', 'subject', 'is_active']
    list_filter = ['test_class', 'is_active']
    inlines = [QuestionInline]

@admin.register(Question)
class QuestionAdmin(SchoolAdminMixin, admin.ModelAdmin):
    list_display = ['test', 'question_text', 'correct_answer', 'marks']
    list_filter = ['test__school']

@admin.register(StudentTestSession)
class StudentTestSessionAdmin(SchoolAdminMixin, admin.ModelAdmin):
    list_display = ['student', 'test', 'is_submitted', 'score', 'start_time']

@admin.register(StudentAnswer)
class StudentAnswerAdmin(SchoolAdminMixin, admin.ModelAdmin):
    list_display = ['session', 'question', 'selected_answer']

@admin.register(TeacherNote)
class TeacherNoteAdmin(SchoolAdminMixin, admin.ModelAdmin):
    list_display = ('student', 'school', 'term', 'session', 'teacher', 'is_approved', 'date')
    list_filter = ('term', 'session', 'is_approved')

@admin.register(Gallery)
class GalleryAdmin(SchoolAdminMixin, admin.ModelAdmin):
    list_display = ('title', 'school', 'category', 'uploaded_at')
    list_filter = ('category',)

@admin.register(CATest)
class CATestAdmin(SchoolAdminMixin, admin.ModelAdmin):
    list_display = ('title', 'subject', 'student_class', 'teacher', 'status', 'is_active', 'test_date', 'access_token')
    list_filter = ('status',)
    list_editable = ('status', 'is_active')

@admin.register(CATestQuestion)
class CATestQuestionAdmin(SchoolAdminMixin, admin.ModelAdmin):
    list_display = ('test', 'question_number', 'question_type')
    list_filter = ('test__school',)

@admin.register(CATestResult)
class CATestResultAdmin(SchoolAdminMixin, admin.ModelAdmin):
    list_display = ('test', 'student_name', 'score', 'percentage')
    list_filter = ('test__school',)

@admin.register(StudentNote)
class StudentNoteAdmin(SchoolAdminMixin, admin.ModelAdmin):
    list_display = ('title', 'student_class', 'subject', 'school', 'teacher', 'term', 'session', 'is_approved')
    list_filter = ('student_class', 'term', 'session', 'is_approved')
    list_editable = ('is_approved',)
    search_fields = ('title', 'note')
    actions = ['approve_and_send_whatsapp']
    def approve_and_send_whatsapp(self, request, queryset):
        sent_count = 0
        for note in queryset.filter(is_approved=False):
            note.is_approved = True
            note.save()
            students = Student.objects.filter(student_class=note.student_class, school=note.school)
            for student in students:
                if student.parent_phone:
                    message = f"*📢 New Teacher's Note - {note.school.name}*\n\n*Class:* {note.student_class}\n*Title:* {note.title}"
                    send_whatsapp_message(student.parent_phone, message)
                    sent_count += 1
        self.message_user(request, f"✅ {sent_count} WhatsApp sent.")

@admin.register(News)
class NewsAdmin(SchoolAdminMixin, admin.ModelAdmin):
    list_display = ('school', 'title', 'date_posted', 'is_active')
    list_filter = ('is_active', 'date_posted')
    list_editable = ('is_active',)

@admin.register(WhyChooseUsCard)
class WhyChooseUsCardAdmin(SchoolAdminMixin, admin.ModelAdmin):
    list_display = ('school', 'title', 'icon', 'order')
    list_editable = ('order',)

admin.site.unregister(User)
@admin.register(User)
class UserAdmin(SchoolAdminMixin, BaseUserAdmin):
    def get_queryset(self, request):
        qs = super(BaseUserAdmin, self).get_queryset(request)
        if request.user.is_superuser:
            return qs
        school = self._get_school(request)
        if not school:
            return qs.filter(id=request.user.id)
        teacher_user_ids = Teacher.objects.filter(school=school).values_list('user_id', flat=True)
        return qs.filter(Q(id__in=teacher_user_ids) | Q(id=request.user.id))

@admin.register(AdmissionApplication)
class AdmissionApplicationAdmin(SchoolAdminMixin, admin.ModelAdmin):
    list_display = ('full_name','class_applying','school','status','parent_phone','applied_on')
    list_filter = ('status',)
    search_fields = ('full_name','parent_phone')
    list_editable = ('status',)

@admin.register(LessonPlan)
class LessonPlanAdmin(admin.ModelAdmin):
    list_display = ('week', 'topic', 'subject', 'student_class', 'teacher', 'school', 'is_approved', 'created_at')
    list_filter = ('is_approved', 'school', 'week')
    search_fields = ('topic', 'subject', 'student_class')
    list_editable = ('is_approved',)  # Principal can click checkbox directly
    actions = ['approve_plans']

    def approve_plans(self, request, queryset):
        queryset.update(is_approved=True)
    approve_plans.short_description = "✅ Approve selected lesson plans"

@admin.register(Psychomotor)
class PsychomotorAdmin(admin.ModelAdmin):
    list_display = ('student', 'term', 'session', 'punctuality', 'neatness')
    list_filter = ('term', 'session', 'student__student_class')