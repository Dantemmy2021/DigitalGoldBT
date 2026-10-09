from django.shortcuts import render, get_object_or_404, redirect
import os
import uuid
from django.urls import reverse
from django.db.models import Q, Sum
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse, HttpResponseForbidden
from django.template.loader import get_template
from django.utils import timezone
from decimal import Decimal, ROUND_HALF_UP
from xhtml2pdf import pisa
from django.contrib.auth.hashers import check_password, make_password
from io import BytesIO
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.conf import settings
from functools import wraps
from collections import defaultdict
from django.shortcuts import get_object_or_404, render, redirect
import xhtml2pdf.pisa as pisa
from results.models import Psychomotor

import qrcode
import base64

from .forms import StudentNoteForm, AdmissionForm
from .models import (
    School, StudentClass, Subject, Student, Teacher, ScratchCard, StudentScore,
    AssessmentComponent, GradeScale, StudentNote, CATest, Attendance, CATestQuestion,
    CATestResult, Test, Question, StudentTestSession, StudentAnswer, StudentSubject,
    Gallery, News, TeacherNote, Staff, StaffAttendance, 
    StudentCASession, StudentCAAnswer, AdmissionApplication  # <-- ADD THIS
)

TERM_CHOICES = [
    ('First Term', 'First Term'),
    ('Second Term', 'Second Term'),
    ('Third Term', 'Third Term'),
]

SESSION_CHOICES = [
    ('2023/2024', '2023/2024'),
    ('2024/2025', '2024/2025'),
    ('2025/2026', '2025/2026'),
    ('2026/2027', '2026/2027'),
]

ALL_TERMS = ['First Term', 'Second Term', 'Third Term']
TERM_ORDER = {'First Term': 1, 'Second Term': 2, 'Third Term': 3}

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta # make sure this is also here

# ADD THIS FUNCTION
def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

# ===== HELPER FUNCTIONS =====
def get_student(request, school=None):
    """Get logged in student from session. Returns None if not logged in"""
    student_id = request.session.get('student_id')
    if not student_id:
        return None
    try:
        student = Student.objects.get(id=student_id)
        if school and student.student_class.school!= school:
            return None
        return student
    except Student.DoesNotExist:
        return None

def get_grade_and_remark(school, score):
    if score is None or score <= 0:
        return "-", "-"
    try:
        score = float(score)
    except:
        score = 0
    grade_obj = GradeScale.objects.filter(school=school, min_score__lte=score, max_score__gte=score).first()
    if grade_obj:
        return grade_obj.grade, grade_obj.remark
    if score >= 70: return "A1", "Excellent"
    elif score >= 60: return "B2", "Very Good"
    elif score >= 50: return "B3", "Good"
    elif score >= 40: return "C5", "Credit"
    elif score >= 35: return "C6", "Pass"
    else: return "F9", "Fail"

def get_student_subject_total(student, subject, term, session):
    total = StudentScore.objects.filter(student=student, subject=subject, term=term, session=session).aggregate(total=Sum('score'))['total']
    return float(total) if total else 0.0

def get_component_score(student, subject, term, session, comp_name):
    score = StudentScore.objects.filter(student=student, subject=subject, term=term, session=session, component__name__iexact=comp_name).first()
    return float(score.score) if score and score.score is not None else 0.0

def is_super_admin(user):
    return user.is_active and user.is_superuser

def is_school_admin_for_school(request, user, school):
    if user.is_superuser and not request.session.get('school_slug', None):
        return True
    if hasattr(user, 'teacher') and user.teacher.school == school:
        return True
    return False

def link_callback(uri, rel):
    """Convert HTML URIs to absolute system paths for xhtml2pdf"""
    sUrl = settings.STATIC_URL
    sRoot = settings.STATIC_ROOT
    mUrl = settings.MEDIA_URL
    mRoot = settings.MEDIA_ROOT

    if uri.startswith(mUrl):
        path = os.path.join(mRoot, uri.replace(mUrl, ""))
    elif uri.startswith(sUrl):
        path = os.path.join(sRoot, uri.replace(sUrl, ""))
    else:
        return uri
    if not os.path.isfile(path):
        return uri
    return path

def send_email_to_student_parents(student, subject, message):
    """Send email to one student's parent"""
    if not student.parent_email:
        return False
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [student.parent_email], fail_silently=False)
    return True

# ===== DECORATORS =====
def teacher_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, school_slug, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('results:teacher_login', school_slug=school_slug)
        school = get_object_or_404(School, slug=school_slug)
        if not hasattr(request.user, 'teacher') and not request.user.is_superuser:
            messages.error(request, "This account is not assigned as a Teacher")
            return redirect('results:teacher_login', school_slug=school_slug)
        if hasattr(request.user, 'teacher') and request.user.teacher.school!= school:
            messages.error(request, "You do not belong to this school")
            return redirect('results:teacher_login', school_slug=school_slug)
        return view_func(request, school_slug, *args, **kwargs)
    return _wrapped_view

def student_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, school_slug, *args, **kwargs):
        student = get_student(request)
        if not student:
            messages.error(request, 'Please login as student first')
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

# ===== GENERAL LOGOUT =====
def custom_logout(request):
    logout(request)
    messages.success(request, "Logged out successfully")
    return redirect('/admin/login/')

def custom_logout_school(request, school_slug):
    school = get_object_or_404(School, slug=school_slug)
    logout(request)
    messages.success(request, "Logged out successfully")
    return redirect('results:portal_login', school_slug=school.slug)


#===== SCHOOL TEACHER LOGIN =====
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib import messages
from django.conf import settings
from django.contrib.auth.decorators import login_required

def school_teacher_login(request, school_slug):
    school = get_object_or_404(School, slug=school_slug)
    
    # If already logged in as teacher of this school, go to dashboard
    if request.user.is_authenticated and hasattr(request.user, 'teacher'):
        if request.user.teacher.school == school:
            return redirect('results:teacher_dashboard', school_slug=school.slug)
        else:
            logout(request)
    
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        
        # Case insensitive username
        try:
            user_obj = User.objects.get(username__iexact=username)
            username = user_obj.username
        except User.DoesNotExist:
            pass

        user = authenticate(request, username=username, password=password)
        if user and user.is_active:
            try:
                teacher = Teacher.objects.get(user=user, school=school)
                login(request, user)
                messages.success(request, f"Welcome {teacher.full_name}")
                return redirect('results:teacher_dashboard', school_slug=school.slug)
            except Teacher.DoesNotExist:
                messages.error(request, f"This account is not a Teacher in {school.name}")
        else:
            messages.error(request, "Invalid Username or Password")
    return render(request, 'results/teacher_login.html', {'school': school})

# ===== TEACHER DASHBOARD - ONLY 1 VERSION =====
@login_required(login_url='results:school_teacher_login')
def teacher_dashboard(request, school_slug):
    school = get_object_or_404(School, slug=school_slug)
    teacher = get_object_or_404(Teacher, user=request.user, school=school)
    
    subjects = teacher.subjects.filter(school=school).order_by('name')
    classes = teacher.classes.filter(school=school).order_by('name')
    students_count = Student.objects.filter(student_class__school=school, student_class__in=classes).distinct().count()
    
    # NEW: Classes where this teacher is the CLASS TEACHER
    class_teacher_classes = StudentClass.objects.filter(school=school, class_teacher=teacher).order_by('name')
    
    context = {
        'teacher': teacher, 
        'school': school, 
        'school_slug': school_slug, 
        'subjects': subjects, 
        'classes': classes, 
        'class_teacher_classes': class_teacher_classes,  # <-- ADDED
        'students_count': students_count,
        'primary_color': getattr(school, 'primary_color', settings.SCHOOL_PRIMARY_COLOR),
    }
    return render(request, 'results/teacher_dashboard.html', context)


# ===== GLOBAL STUDENT LOGIN ======
def student_login_global(request):
    if request.method == 'POST':
        school_slug = request.POST.get('school_slug')
        if school_slug:
            return redirect('results:student_login', school_slug=school_slug)
        messages.error(request, "Please enter your school code")
    schools = School.objects.all()
    return render(request, 'results/student_login_global.html', {'schools': schools})

# ===== SCHOOL STUDENT LOGIN ======
def student_login(request, school_slug):
    school = get_object_or_404(School, slug=school_slug)
    if request.method == 'POST':
        admission_no = request.POST.get('admission_no','').strip().upper()
        password = request.POST.get('password','').strip()
        student = Student.objects.filter(admission_no=admission_no, student_class__school=school).first()
        if student and check_password(password, student.password):
            request.session['student_id'] = student.id
            request.session['school_id'] = school.id
            request.session['school_slug'] = school.slug
            messages.success(request, f"Welcome {student.full_name}")
            return redirect('results:student_dashboard', school_slug=school_slug)
        else:
            messages.error(request, 'Invalid Admission Number or Password')
    return render(request, 'results/student_login.html', {'school': school})

# ===== STUDENT LOGOUT ======
def student_logout(request, school_slug):
    school = get_object_or_404(School, slug=school_slug)
    for key in ['student_id', 'school_id', 'school_slug']:
        request.session.pop(key, None)
    messages.success(request, "Logged out successfully")
    return redirect('results:student_login', school_slug=school.slug)

# ===== SCHOOL ADMIN ROUTING =====
def school_admin_login(request, school_slug):
    school = get_object_or_404(School, slug=school_slug)
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user and user.is_active and user.is_staff:
            if user.is_superuser or (hasattr(user, 'teacher') and user.teacher.school == school):
                login(request, user)
                request.session['school_slug'] = school_slug
                request.session.modified = True
                messages.success(request, f"Welcome to {school.name} Admin")
                return redirect('results:school_admin_redirect', school_slug=school_slug)
            else:
                messages.error(request, f"This account does not belong to {school.name}")
        else:
            messages.error(request, "Invalid Username or Password")
    return render(request, 'results/school_admin_login.html', {'school': school})

@login_required
def school_admin_redirect(request, school_slug):
    school = get_object_or_404(School, slug=school_slug)
    if not request.user.is_authenticated:
        return redirect('results:school_admin_login', school_slug=school_slug)
    if not request.user.is_superuser and not (hasattr(request.user, 'teacher') and request.user.teacher.school == school):
        messages.error(request, "You don't have access to this school")
        return redirect('results:school_admin_login', school_slug=school_slug)

    request.session['school_slug'] = school_slug
    request.session.modified = True

    students = Student.objects.filter(student_class__school=school).select_related('student_class').order_by('student_class__name', 'full_name')
    classes = StudentClass.objects.filter(school=school)
    teachers = Teacher.objects.filter(school=school).order_by('full_name')

    context = {
        'school': school, 
        'students': students, 
        'classes': classes, 
        'total_students': students.count(),
        'total_teachers': teachers.count(),  # now shows 7
        'teachers': teachers,
    }
    return render(request, 'results/school_admin_dashboard.html', context)

# ===== SCHOOL HOMEPAGE =====
def school_landing(request, school_slug):
    school = get_object_or_404(School, slug=school_slug)
    gallery = Gallery.objects.filter(school=school)
    news = News.objects.filter(school=school, is_active=True)[:3]
    why_cards = school.why_cards.all().order_by('order')
    context = {
        'school': school, 
        'gallery': gallery, 
        'news': news,
        'why_cards': why_cards
    }
    return render(request, 'results/school_landing.html', context)
def news_detail(request, school_slug, news_id):
    school = get_object_or_404(School, slug=school_slug)
    news_item = get_object_or_404(News, id=news_id, school=school)
    return render(request, 'results/news_detail.html', {'school': school, 'news_item': news_item})

# ===== HOME / REDIRECT =====
@login_required(login_url='/admin/login/')
def home_redirect(request):
    if request.user.is_staff and request.user.is_superuser:
        return redirect('/admin/')
    else:
        return redirect('results:teacher_dashboard', school_slug=request.user.teacher.school.slug)

#====== TEACHER GIVE NOTE ======
@login_required
def teacher_give_note(request, school_slug):
    school = get_object_or_404(School, slug=school_slug)
    teacher = request.user.teacher
    if request.method == 'POST':
        form = StudentNoteForm(request.POST, request.FILES, school=school)
        if form.is_valid():
            note = form.save(commit=False)
            note.school = school
            note.teacher = teacher
            note.is_approved = False
            note.save()
            messages.success(request, f'Note "{note.title}" uploaded successfully!')
            return redirect('results:teacher_dashboard', school_slug=school.slug)
        else:
            messages.error(request, 'Please fix the errors below')
    else:
        form = StudentNoteForm(school=school)
    context = {'form': form, 'school': school}
    return render(request, 'results/teacher_give_note.html', context)

# ===== UPGRADE 2: CA TEST =====
from django.utils import timezone

@login_required(login_url='login')
@teacher_required
def teacher_ca_test(request, school_slug):
    school = get_object_or_404(School, slug=school_slug)
    teacher = get_object_or_404(Teacher, user=request.user, school=school)

    if request.method == 'POST':
        # 1. CREATE TEST AS PENDING
        test = CATest.objects.create(
            school=school,
            teacher=teacher,
            subject=get_object_or_404(Subject, id=request.POST.get('subject')),
            student_class=get_object_or_404(StudentClass, id=request.POST.get('student_class')),
            title=request.POST.get('title'),
            instructions=request.POST.get('instructions'),
            test_date=request.POST.get('test_date'),
            max_score=request.POST.get('max_score'),
            duration_minutes=int(request.POST.get('duration_minutes', 30)), # <-- ADDED THIS
            term=request.POST.get('term'),
            session=school.current_session,
            status='pending', # NEW
            is_active=False # NEW: not live until approved
        )

        # 2. CREATE QUESTIONS WITH IMAGES
        question_texts = request.POST.getlist('question_text[]')
        question_images = request.FILES.getlist('question_image[]')
        marks = request.POST.getlist('marks[]')
        option_a_list = request.POST.getlist('option_a[]')
        option_b_list = request.POST.getlist('option_b[]')
        option_c_list = request.POST.getlist('option_c[]')
        option_d_list = request.POST.getlist('option_d[]')
        correct_answers = request.POST.getlist('correct_answer[]')

        for i, q_text in enumerate(question_texts):
            img = question_images[i] if i < len(question_images) else None
            mark = marks[i] if i < len(marks) else 1
            opt_a = option_a_list[i] if i < len(option_a_list) else ''
            opt_b = option_b_list[i] if i < len(option_b_list) else ''
            opt_c = option_c_list[i] if i < len(option_c_list) else ''
            opt_d = option_d_list[i] if i < len(option_d_list) else ''
            correct = correct_answers[i] if i < len(correct_answers) else ''

            if q_text.strip():
                CATestQuestion.objects.create(
                    test=test,
                    question_number=i+1,
                    question_text=q_text,
                    question_image=img,
                    marks=mark,
                    option_a=opt_a,
                    option_b=opt_b,
                    option_c=opt_c,
                    option_d=opt_d,
                    correct_answer=correct
                )

        messages.success(request, f"CA Test '{test.title}' submitted for School Admin Approval")
        return redirect('results:teacher_dashboard', school_slug=school.slug)

    context = {
        'school': school,
        'school_slug': school_slug,
        'teacher': teacher,
        'classes': teacher.classes.all(),
        'subjects': teacher.subjects.all(),
        'terms': TERM_CHOICES
    }
    return render(request, 'results/teacher_give_test.html', context)

from datetime import timedelta # ADD THIS AT TOP OF views.py

# ===== CA TEST =====
@student_required
def take_ca(request, school_slug, ca_id):
    school = get_object_or_404(School, slug=school_slug)
    ca_test = get_object_or_404(CATest, id=ca_id, school=school, is_active=True, status='approved')
    student = get_student(request, school)

    if not student:
        messages.error(request, 'Student not found. Please login again.')
        return redirect('results:student_login', school_slug=school_slug)

    if student.student_class!= ca_test.student_class:
        messages.error(request, 'You are not allowed to take this test')
        return redirect('results:student_dashboard', school_slug=school_slug)

    # ========== WIFI/IP CHECK ==========
    client_ip = get_client_ip(request)
    allowed_ips = [ip.strip() for ip in school.allowed_ips.split(',')] if school.allowed_ips else []

    if allowed_ips and client_ip not in allowed_ips:
        messages.error(request, f'Access Denied. You must be on school WiFi to take this CA. Detected IP: {client_ip}')
        return redirect('results:student_dashboard', school_slug=school_slug)
    # ========== END WIFI CHECK ==========

    session, created = StudentCASession.objects.get_or_create(
        student=student,
        ca_test=ca_test,
        defaults={'start_time': timezone.now()}
    )

    if session.is_submitted:
        messages.warning(request, 'You have already submitted this CA')
        return redirect('results:student_dashboard', school_slug=school_slug)

    questions = list(ca_test.questions.all())
    if not questions:
        messages.error(request, 'No questions added to this CA test yet')
        return redirect('results:student_dashboard', school_slug=school_slug)

    # ========== TIMER CHECK ==========
    time_used = timezone.now() - session.start_time
    time_limit = timedelta(minutes=ca_test.duration_minutes)

    if time_used >= time_limit:
        # Auto submit because time is up
        session.is_submitted = True
        session.end_time = timezone.now()

        score = sum(ans.question.marks for ans in session.answers.select_related('question') if ans.selected_answer == ans.question.correct_answer)
        session.score = score
        session.save()

        total_possible = sum(q.marks for q in questions)
        component, _ = AssessmentComponent.objects.get_or_create(
            school=school,
            section=student.student_class.section,
            name="CA",
            defaults={'max_score': total_possible, 'order': 98}
        )
        StudentScore.objects.update_or_create(
            student=student,
            subject=ca_test.subject,
            term=school.current_term,
            session=school.current_session,
            component=component,
            defaults={'score': session.score}
        )
        messages.error(request, f'Time up! CA Auto-submitted. Score: {session.score}/{total_possible}')
        return redirect('results:student_dashboard', school_slug=school_slug)
    # ========== END TIMER CHECK ==========

    current_q_num = int(request.GET.get('q', 1))
    if current_q_num < 1: current_q_num = 1
    if current_q_num > len(questions): current_q_num = len(questions)

    if request.method == "POST":
        action = request.POST.get('action')
        question_id = request.POST.get('question_id')
        answer = request.POST.get('answer')

        if answer and question_id:
            StudentCAAnswer.objects.update_or_create(
                session=session,
                question_id=question_id,
                defaults={'selected_answer': answer}
            )

        current_q_num += -1 if action == 'prev' else 1

        if current_q_num > len(questions):
            session.is_submitted = True
            session.end_time = timezone.now()
            score = sum(ans.question.marks for ans in session.answers.select_related('question') if ans.selected_answer == ans.question.correct_answer)
            session.score = score
            session.save()

            total_possible = sum(q.marks for q in questions)
            component, _ = AssessmentComponent.objects.get_or_create(
                school=school,
                section=student.student_class.section,
                name="CA",
                defaults={'max_score': total_possible, 'order': 98}
            )
            StudentScore.objects.update_or_create(
                student=student,
                subject=ca_test.subject,
                term=school.current_term,
                session=school.current_session,
                component=component,
                defaults={'score': session.score}
            )
            messages.success(request, f'CA Submitted! Your score: {session.score}/{total_possible}')
            return redirect('results:student_dashboard', school_slug=school_slug)

        return redirect(f"{reverse('results:take_ca', args=[school_slug, ca_id])}?q={current_q_num}")

    question = questions[current_q_num - 1]
    prev_answer_obj = StudentCAAnswer.objects.filter(session=session, question_id=question.id).first()
    answered_ids = list(StudentCAAnswer.objects.filter(session=session).values_list('question_id', flat=True))

    context = {
        'question': question,
        'question_number': current_q_num,
        'total_questions': len(questions),
        'is_last': current_q_num == len(questions),
        'session': session,
        'school': school,
        'school_slug': school_slug,
        'test': ca_test,
        'prev_answer': prev_answer_obj.selected_answer if prev_answer_obj else None,
        'answered_ids': answered_ids,
    }
    return render(request, 'results/take_test.html', context)

# ===== UPGRADE 3: ATTENDANCE =====
@login_required(login_url='login')
@teacher_required
def teacher_take_attendance(request, school_slug):
    school = get_object_or_404(School, slug=school_slug)
    teacher = get_object_or_404(Teacher, user=request.user, school=school)
    classes = StudentClass.objects.filter(school=school, class_teacher=teacher)
    selected_class = None
    students = []
    today = timezone.now().date()
    if request.GET.get('class_id'):
        selected_class = get_object_or_404(StudentClass, id=request.GET.get('class_id'))
        if selected_class.class_teacher!= teacher:
            raise PermissionDenied("You are not the class teacher for this class")
        students = Student.objects.filter(student_class__school=school, student_class=selected_class).order_by('full_name')
    if request.method == 'POST':
        class_id = request.POST.get('class_id')
        selected_class = get_object_or_404(StudentClass, id=class_id)
        if selected_class.class_teacher!= teacher:
            raise PermissionDenied("You are not the class teacher for this class")
        for student in Student.objects.filter(student_class=selected_class):
            status = request.POST.get(f'status_{student.id}')
            if status:
                Attendance.objects.update_or_create(
                    student=student, date=today,
                    defaults={'school': school, 'student_class': selected_class, 'teacher': teacher, 'term': school.current_term, 'session': school.current_session, 'status': status}
                )
        messages.success(request, "Attendance saved")
        return redirect('results:teacher_dashboard', school_slug=school.slug)
    context = {'school': school, 'school_slug': school_slug, 'teacher': teacher, 'classes': classes, 'selected_class': selected_class, 'students': students, 'today': today}
    return render(request, 'results/teacher_take_attendance.html', context)

# ===== TEACHER SCORE ENTRY - FIXED FOR STUDENT SUBJECTS =====
@login_required(login_url='login')
@teacher_required
def enter_scores(request, school_slug, subject_id):
    school = get_object_or_404(School, slug=school_slug)
    teacher = get_object_or_404(Teacher, user=request.user, school=school)
    components = AssessmentComponent.objects.filter(school=school).order_by('order')
    selected_subject = get_object_or_404(Subject, id=subject_id, school=school)
    
    if selected_subject not in teacher.subjects.all():
        messages.error(request, "You are not assigned to this subject")
        return redirect('results:teacher_dashboard', school_slug=school.slug)
    
    selected_class = None
    students = []
    selected_term = request.GET.get('term', school.current_term)
    selected_session = request.GET.get('session', school.current_session)
    class_id = request.GET.get('class') or request.POST.get('class')
    
    if class_id:
        selected_class = get_object_or_404(StudentClass, id=class_id, school=school)
        if selected_class not in teacher.classes.all():
            messages.error(request, "You are not assigned to this class")
            return redirect('results:teacher_dashboard', school_slug=school.slug)
        
        # FIX: ONLY STUDENTS OFFERING THIS SUBJECT
        students = Student.objects.filter(
            student_class__school=school,
            student_class=selected_class,
            offered_subjects__subject=selected_subject,
        ).distinct().order_by('full_name')
    
    if request.method == 'POST':
        selected_term = request.POST.get('term', selected_term)
        selected_session = request.POST.get('session', selected_session)
        
        saved_count = 0
        for student in students:
            for comp in components:
                score_val = request.POST.get(f'score_{student.id}_{comp.id}')
                if score_val and score_val.strip() != '':
                    try:
                        score_val = Decimal(score_val).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    except:
                        continue
                    if score_val > comp.max_score:
                        messages.error(request, f"{student.full_name}: {comp.name} cannot be more than {comp.max_score}")
                        return redirect('results:enter_scores', school_slug=school.slug, subject_id=selected_subject.id)
                    if score_val < 0:
                        messages.error(request, "Score cannot be negative")
                        return redirect('results:enter_scores', school_slug=school.slug, subject_id=selected_subject.id)
                    
                    StudentScore.objects.update_or_create(
                        student=student, 
                        subject=selected_subject, 
                        component=comp,
                        term=selected_term, 
                        session=selected_session, 
                        defaults={'score': score_val}
                    )
                    saved_count += 1
        
        if saved_count > 0:
            messages.success(request, f"{saved_count} scores saved for {selected_subject.name}")
        return redirect(f"{request.path}?class={class_id}&term={selected_term}&session={selected_session}")
    
    scores_dict = {}
    if students and selected_subject:
        existing_scores = StudentScore.objects.filter(
            student__in=students, 
            subject=selected_subject, 
            term=selected_term, 
            session=selected_session
        )
        for score_obj in existing_scores:
            scores_dict.setdefault(score_obj.student.id, {})[score_obj.component.id] = score_obj.score
        for student in students:
            student_scores = scores_dict.get(student.id, {})
            total = sum([float(s) for s in student_scores.values() if s is not None])
            scores_dict.setdefault(student.id, {})['_total'] = total
    
    context = {
        'teacher': teacher, 
        'school': school, 
        'school_slug': school_slug, 
        'subjects': teacher.subjects.all(), 
        'classes': teacher.classes.all(), 
        'components': components, 
        'students': students, 
        'scores_dict': scores_dict, 
        'selected_subject': selected_subject, 
        'selected_class': selected_class, 
        'term_choices': TERM_CHOICES, 
        'session_choices': SESSION_CHOICES, 
        'selected_term': selected_term, 
        'selected_session': selected_session, 
        'is_locked': False  # REMOVED LOCK CHECK
    }
    return render(request, 'results/enter_scores.html', context)

# ===== TEACHER PRINT STUDENT RESULT =====
@login_required(login_url='login')
@teacher_required
def print_result(request, school_slug, student_id):
    school = get_object_or_404(School, slug=school_slug)
    teacher = get_object_or_404(Teacher, user=request.user, school=school)
    student = get_object_or_404(Student, id=student_id, student_class__school=school)
    
    if student.student_class not in teacher.classes.all() and not request.user.is_superuser:
        messages.error(request, "You can only print results for students in your class")
        return redirect('results:teacher_dashboard', school_slug=school.slug)
        
    term = request.GET.get('term', school.current_term)
    session = request.GET.get('session', school.current_session)
    components = AssessmentComponent.objects.filter(school=school).order_by('order')
    
    subjects = Subject.objects.filter(
        school=school, student_class=student.student_class,
        studentsubject__student=student, studentsubject__session=session
    ).distinct().order_by('name')
    
    all_terms = ALL_TERMS
    term_index = all_terms.index(term) if term in all_terms else 2
    
    results_data = []
    term_total = Decimal('0.0')
    
    for subject in subjects:
        subject_total = Decimal(str(get_student_subject_total(student, subject, term, session)))
        if subject_total <= 0:
            continue
        term_total += subject_total
        grade, remark = get_grade_and_remark(school, float(subject_total))
        comp_scores = {comp.name: get_component_score(student, subject, term, session, comp.name) for comp in components}
        
        t1_score = Decimal(str(get_student_subject_total(student, subject, 'First Term', session)))
        t2_score = Decimal(str(get_student_subject_total(student, subject, 'Second Term', session)))
        
        if term == 'Third Term':
            count_terms = 0
            sum_terms = Decimal('0.0')
            if t1_score > 0:
                sum_terms += t1_score
                count_terms += 1
            if t2_score > 0:
                sum_terms += t2_score
                count_terms += 1
            if subject_total > 0:
                sum_terms += subject_total
                count_terms += 1
            
            cumulative_avg_subject = round(float(sum_terms / count_terms), 2) if count_terms > 0 else float(subject_total)
            cum_grade, cum_remark = get_grade_and_remark(school, cumulative_avg_subject)
        else:
            cumulative_avg_subject = float(subject_total)
            cum_grade, cum_remark = grade, remark

        results_data.append({
            'subject': subject.name,
            'components': comp_scores,
            'total': subject_total,
            'grade': grade,
            'remark': remark,
            'term1': t1_score,
            'term2': t2_score,
            'cumulative': cumulative_avg_subject,
            'cum_grade': cum_grade,
            'cum_remark': cum_remark
        })
    
    count = len(results_data)
    average = round(float(term_total / count), 2) if count > 0 else 0.0
    
    if term == 'Third Term' and count > 0:
        cumulative_avg = round(sum([d['cumulative'] for d in results_data]) / count, 2)
    else:
        cumulative_avg = average

    # === PSYCHOMOTOR FETCH ===
    psychomotor = Psychomotor.objects.filter(student=student, term=term, session=session).first()
    
    context = {
        'school': school, 'school_slug': school_slug, 'teacher': teacher, 'student': student,
        'results_data': results_data, 'components': components, 'term': term, 'session': session,
        'term_choices': TERM_CHOICES, 'session_choices': SESSION_CHOICES,
        'total_score': term_total, 'average': average, 'cumulative_avg': cumulative_avg,
        'is_third_term': term == 'Third Term',
        'psychomotor': psychomotor,  # <-- added
    }
    return render(request, 'results/print_result.html', context)


# ===== PARENT VIEW RESULT =====
def view_result(request, school_slug):
    school = get_object_or_404(School, slug=school_slug)
    student_id = request.session.get('student_id')
    if not student_id:
        messages.error(request, "Please enter Admission No and PIN first")
        return redirect('results:parent_login', school_slug=school.slug)
    
    student = get_object_or_404(Student, id=student_id, student_class__school=school)
    term = request.GET.get('term', school.current_term)
    session = request.GET.get('session', school.current_session)
    components = AssessmentComponent.objects.filter(school=school).order_by('order')
    
    subjects = Subject.objects.filter(
        school=school, student_class=student.student_class,
        studentsubject__student=student, studentsubject__session=session
    ).distinct().order_by('name')
    
    all_terms = ALL_TERMS
    results_data = []
    total_score = Decimal('0.0')
    
    for subject in subjects:
        term_total = Decimal(str(get_student_subject_total(student, subject, term, session)))
        if term_total == 0:
            continue
        
        comp_dict = {comp.name: get_component_score(student, subject, term, session, comp.name) for comp in components}
        grade, remark = get_grade_and_remark(school, float(term_total))
        
        # --- FIX FOR 3RD TERM COLUMNS ---
        t1 = Decimal(str(get_student_subject_total(student, subject, 'First Term', session)))
        t2 = Decimal(str(get_student_subject_total(student, subject, 'Second Term', session)))
        t3 = Decimal(str(get_student_subject_total(student, subject, 'Third Term', session))) if term == 'Third Term' else term_total
        
        if term == 'Third Term':
            sum_terms = Decimal('0.0')
            count_terms = 0
            if t1 > 0: 
                sum_terms += t1
                count_terms += 1
            if t2 > 0: 
                sum_terms += t2
                count_terms += 1
            if t3 > 0: 
                sum_terms += t3
                count_terms += 1
            
            cum_avg = round(float(sum_terms / count_terms), 2) if count_terms > 0 else 0.0
            cum_grade, cum_remark = get_grade_and_remark(school, cum_avg)
        else:
            cum_avg = float(term_total)
            cum_grade, cum_remark = grade, remark

        results_data.append({
            'subject': subject.name,
            'components': comp_dict,
            'total': term_total,
            'grade': grade,
            'remark': remark,
            'total_first_term': t1,  # 1ST TERM %
            'total_second_term': t2, # 2ND TERM %
            'cumulative_avg': cum_avg, # CUM AVG
            'cum_grade': cum_grade,
            'cum_remark': cum_remark
        })
        total_score += term_total

    count = len(results_data)
    average = round(float(total_score / count), 2) if count > 0 else 0.0
    
    # For 3rd term, overall average = average of cumulative averages
    if term == 'Third Term' and count > 0:
        cumulative_avg = round(sum([r['cumulative_avg'] for r in results_data]) / count, 2)
    else:
        cumulative_avg = average

    context = {
        'school': school, 'student': student, 'term': term, 'session': session,
        'components': components, 'results_data': results_data, 'all_terms': all_terms,
        'total_score': total_score, 'average': average, 
        'cumulative_avg': cumulative_avg,
        'is_third_term': term == 'Third Term'
    }
    return render(request, 'results/view_result.html', context)

#====== RESULT/SCHOOL FEES ALERT =========
def send_fee_reminder_emails():
    students = Student.objects.exclude(parent_email__isnull=True).exclude(parent_email='')
    sent_count = 0
    for student in students:
        parent_email = student.parent_email
        student_name = student.full_name
        parent_name = student.parent_name
        subject = f'School Fees Due - {student_name}'
        message = f"Dear {parent_name},\n\nThis is a reminder that school fees for {student_name} - {student.admission_no} is currently due.\n\nPlease log in to the OKC Portal to make payment as soon as possible.\n\nThank you.\nOKC Portal Admin\nAmazing Grace Schools\n"
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [parent_email])
        sent_count += 1
    return f"Sent {sent_count} fee reminder emails"

def send_result_out_emails():
    students = Student.objects.exclude(parent_email__isnull=True).exclude(parent_email='')
    sent_count = 0
    for student in students:
        parent_email = student.parent_email
        student_name = student.full_name
        parent_name = student.parent_name
        subject = f'Result is Out - {student_name}'
        message = f"Dear {parent_name},\n\nThe result for {student_name} - {student.admission_no} is now available on the OKC Portal.\n\nPlease log in to https://yourportal.com to view and download the result.\n\nThank you.\nOKC Portal Admin\nAmazing Grace Schools\n"
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [parent_email])
        sent_count += 1
    return f"Sent {sent_count} result notification emails"


# ===== PARENT PRINT RESULT WITH ATTENDANCE =====
def parent_print_result(request, school_slug, student_id):
    school = get_object_or_404(School, slug=school_slug)
    session_student_id = request.session.get('student_id')
    
    if not session_student_id or int(session_student_id) != int(student_id):
        messages.error(request, "Please enter Admission No and PIN first")
        return redirect('results:parent_login', school_slug=school.slug)
    
    student = get_object_or_404(Student, id=student_id, student_class__school=school)
    term = request.GET.get('term', school.current_term)
    session = request.GET.get('session', school.current_session)
    components = AssessmentComponent.objects.filter(school=school).order_by('order')
    
    subjects = Subject.objects.filter(
        school=school, 
        studentsubject__student=student
    ).distinct().order_by('name')
    
    all_terms = ALL_TERMS
    results_data = []
    total_score = Decimal('0.00')
    
    for subject in subjects:
        term_total = Decimal(get_student_subject_total(student, subject, term, session) or 0)
        if term_total == Decimal('0.00'):
            continue
        
        comp_dict = {
            comp.name: Decimal(get_component_score(student, subject, term, session, comp.name) or 0) 
            for comp in components
        }
        grade, remark = get_grade_and_remark(school, term_total)
        
        total_first_term = total_second_term = total_third_term = overall_total = Decimal('0.00')
        cumulative_avg_sub = Decimal('0.00')
        cum_grade = cum_remark = ""
        
        if term == 'Third Term':
            for t in all_terms:
                t_total = Decimal(get_student_subject_total(student, subject, t, session) or 0)
                if t == 'First Term': total_first_term = t_total
                if t == 'Second Term': total_second_term = t_total
                if t == 'Third Term': total_third_term = t_total
            overall_total = total_first_term + total_second_term + total_third_term
            cumulative_avg_sub = round(overall_total / Decimal('3'), 2) if overall_total > 0 else Decimal('0.00')
            cum_grade, cum_remark = get_grade_and_remark(school, cumulative_avg_sub)
        
        results_data.append({
            'subject': subject.name, 
            'components': comp_dict, 
            'total': term_total, 
            'grade': grade, 
            'remark': remark, 
            'total_first_term': total_first_term, 
            'total_second_term': total_second_term, 
            'total_third_term': total_third_term, 
            'overall_total': overall_total,
            'cumulative_avg': cumulative_avg_sub,
            'cum_grade': cum_grade,
            'cum_remark': cum_remark,
        })
        total_score += term_total
    
    average = round(total_score / Decimal(len(results_data)), 2) if results_data else Decimal('0.00')
    term_index = all_terms.index(term) if term in all_terms else 2
    divisor = Decimal(term_index + 1)
    is_third_term = (term == 'Third Term')
    
    try:
        from .models import Result
        all_sessions = list(Result.objects.filter(student=student).values_list('session', flat=True).distinct().order_by('-session'))
    except:
        all_sessions = []
    if not all_sessions:
        all_sessions = [school.current_session]
    
    if is_third_term:
        grand_total = Decimal('0.00')
        for subject in subjects:
            for t in all_terms:
                grand_total += Decimal(get_student_subject_total(student, subject, t, session) or 0)
        num_subjects = len(results_data) if results_data else 1
        cumulative_avg = round(grand_total / (Decimal(num_subjects) * Decimal('3')), 2) if grand_total > 0 else average
    else:
        cumulative_avg = average

    # ===== PSYCHOMOTOR =====
    try:
        from .models import Psychomotor
        from core.models import Psychomotor as CorePsychomotor
    except:
        CorePsychomotor = None
    try:
        PsychomotorModel = CorePsychomotor if CorePsychomotor else None
        if not PsychomotorModel:
            from .models import Psychomotor as LocalPsycho
            PsychomotorModel = LocalPsycho
        psychomotor = PsychomotorModel.objects.filter(student=student, term=term, session=session).first()
        if not psychomotor:
            alt_map = {'First Term': '1st Term', 'Second Term': '2nd Term', 'Third Term': '3rd Term'}
            alt_term = alt_map.get(term, term)
            psychomotor = PsychomotorModel.objects.filter(student=student, term=alt_term, session=session).first()
        if not psychomotor:
            psychomotor = PsychomotorModel.objects.filter(student=student, session=session).order_by('-id').first()
        if not psychomotor:
            psychomotor = PsychomotorModel.objects.filter(student=student).order_by('-id').first()
    except Exception:
        psychomotor = None

    # ===== ATTENDANCE - NEW =====
    try:
        # Try core.models first (where your Attendance is)
        try:
            from core.models import Attendance as AttModel
        except:
            from .models import Attendance as AttModel
        
        att_qs = AttModel.objects.filter(student=student, term=term, session=session)
        # School opened = distinct dates for this class in this term/session
        opened_qs = AttModel.objects.filter(student_class=student.student_class, term=term, session=session).values('date').distinct()
        total_opened = opened_qs.count()
        
        total_present = att_qs.filter(status__in=['Present', 'Late']).count()
        total_absent = att_qs.filter(status='Absent').count()
        total_late = att_qs.filter(status='Late').count()
        
        if total_opened == 0:
            total_opened = att_qs.count()  # fallback
        
        att_percent = round((total_present / total_opened * 100), 1) if total_opened > 0 else 0
        
        attendance = {
            'opened': total_opened,
            'present': total_present,
            'absent': total_absent,
            'late': total_late,
            'percentage': att_percent
        }
    except Exception as e:
        attendance = None
    
    context = {
        'school': school, 
        'student': student, 
        'term': term, 
        'session': session, 
        'components': components, 
        'results_data': results_data, 
        'total_score': total_score, 
        'average': average, 
        'cumulative_avg': cumulative_avg, 
        'divisor': divisor,
        'is_third_term': is_third_term,
        'all_terms': all_terms,
        'all_sessions': all_sessions,
        'psychomotor': psychomotor,
        'attendance': attendance,  # <-- NEW
    }
    return render(request, 'results/parent_print_result.html', context)

#====== PARENT DOWNLOAD RESULT ======
def parent_download_result(request, school_slug, student_id):
    school = get_object_or_404(School, slug=school_slug)
    session_student_id = request.session.get('student_id')
    
    if not session_student_id or int(session_student_id) != int(student_id):
        messages.error(request, "Please enter Admission No and PIN first")
        return redirect('results:parent_login', school_slug=school.slug)
    
    student = get_object_or_404(Student, id=student_id, student_class__school=school)
    term = request.GET.get('term', school.current_term)
    session = request.GET.get('session', school.current_session)
    components = AssessmentComponent.objects.filter(school=school).order_by('order')
    
    subjects = Subject.objects.filter(
        school=school, 
        studentsubject__student=student
    ).distinct().order_by('name')
    
    all_terms = ALL_TERMS
    results_data = []
    total_score = Decimal('0.00')
    
    for subject in subjects:
        term_total = Decimal(get_student_subject_total(student, subject, term, session) or 0)
        if term_total == Decimal('0.00'):
            continue
        
        comp_dict = {
            comp.name: Decimal(get_component_score(student, subject, term, session, comp.name) or 0) 
            for comp in components
        }
        grade, remark = get_grade_and_remark(school, term_total)
        
        total_first_term = total_second_term = total_third_term = overall_total = Decimal('0.00')
        cumulative_avg_sub = Decimal('0.00')
        cum_grade = cum_remark = ""
        
        if term == 'Third Term':
            for t in all_terms:
                t_total = Decimal(get_student_subject_total(student, subject, t, session) or 0)
                if t == 'First Term': total_first_term = t_total
                if t == 'Second Term': total_second_term = t_total
                if t == 'Third Term': total_third_term = t_total
            overall_total = total_first_term + total_second_term + total_third_term
            cumulative_avg_sub = round(overall_total / Decimal('3'), 2) if overall_total > 0 else Decimal('0.00')
            cum_grade, cum_remark = get_grade_and_remark(school, cumulative_avg_sub)
        
        results_data.append({
            'subject': subject.name, 
            'components': comp_dict, 
            'total': term_total, 
            'grade': grade, 
            'remark': remark, 
            'total_first_term': total_first_term, 
            'total_second_term': total_second_term, 
            'total_third_term': total_third_term, 
            'overall_total': overall_total,
            'cumulative_avg': cumulative_avg_sub,
            'cum_grade': cum_grade,
            'cum_remark': cum_remark,
        })
        total_score += term_total
    
    average = round(total_score / Decimal(len(results_data)), 2) if results_data else Decimal('0.00')
    is_third_term = (term == 'Third Term')
    
    if is_third_term:
        grand_total = Decimal('0.00')
        for subject in subjects:
            for t in all_terms:
                grand_total += Decimal(get_student_subject_total(student, subject, t, session) or 0)
        num_subjects = len(results_data) if results_data else 1
        cumulative_avg = round(grand_total / (Decimal(num_subjects) * Decimal('3')), 2) if grand_total > 0 else average
    else:
        cumulative_avg = average

    try:
        try:
            from core.models import Psychomotor as CorePsychomotor
        except:
            CorePsychomotor = None
        if CorePsychomotor:
            PsychomotorModel = CorePsychomotor
        else:
            from .models import Psychomotor as PsychomotorModel
        psychomotor = PsychomotorModel.objects.filter(student=student, term=term, session=session).first()
        if not psychomotor:
            psychomotor = PsychomotorModel.objects.filter(student=student, session=session).order_by('-id').first()
        if not psychomotor:
            psychomotor = PsychomotorModel.objects.filter(student=student).order_by('-id').first()
    except Exception:
        psychomotor = None

    # ===== ATTENDANCE FOR PDF - NEW =====
    try:
        try:
            from core.models import Attendance as AttModel
        except:
            from .models import Attendance as AttModel
        
        att_qs = AttModel.objects.filter(student=student, term=term, session=session)
        opened_qs = AttModel.objects.filter(student_class=student.student_class, term=term, session=session).values('date').distinct()
        total_opened = opened_qs.count()
        total_present = att_qs.filter(status__in=['Present', 'Late']).count()
        total_absent = att_qs.filter(status='Absent').count()
        total_late = att_qs.filter(status='Late').count()
        if total_opened == 0:
            total_opened = att_qs.count()
        att_percent = round((total_present / total_opened * 100), 1) if total_opened > 0 else 0
        attendance = {
            'opened': total_opened,
            'present': total_present,
            'absent': total_absent,
            'late': total_late,
            'percentage': att_percent
        }
    except Exception:
        attendance = None
    
    context = {
        'school': school, 
        'student': student, 
        'term': term, 
        'session': session, 
        'components': components, 
        'results_data': results_data, 
        'total_score': total_score, 
        'average': average,
        'cumulative_avg': cumulative_avg,
        'is_third_term': is_third_term,
        'psychomotor': psychomotor,
        'attendance': attendance,
    }
    
    template = get_template('results/parent_print_result.html')
    html = template.render(context)
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{student.admission_no}_{term}_Result.pdf"'
    pisa.CreatePDF(html, dest=response, link_callback=link_callback)
    return response

# ===== ADMIN PRINT SINGLE STUDENT =====
@login_required
def admin_print_student(request, school_slug, student_id):
    school = get_object_or_404(School, slug=school_slug)
    if not is_school_admin_for_school(request, request.user, school):
        raise PermissionDenied
    student = get_object_or_404(Student, id=student_id, student_class__school=school)
    term = request.GET.get('term', school.current_term)
    session = request.GET.get('session', school.current_session) or "2025/2026"
    components = AssessmentComponent.objects.filter(school=school).order_by('order')
    subjects = Subject.objects.filter(school=school, student_class=student.student_class, studentsubject__student=student, studentsubject__session=session).distinct().order_by('name')
    subject_results = []
    for subject in subjects:
        current = get_student_subject_total(student, subject, term, session)
        grade, remark = get_grade_and_remark(school, current) if current > 0 else ('-', '-')
        comp_scores = []
        for comp in components:
            comp_score = get_component_score(student, subject, term, session, comp.name)
            comp_scores.append({'name': comp.name, 'score': comp_score if comp_score > 0 else '-'})
        subject_results.append({'subject': subject, 'components': comp_scores, 'total': current if current > 0 else '-', 'grade': grade, 'remark': remark})
    context = {'school': school, 'student': student, 'term': term, 'session': session, 'subjects': subject_results, 'components': components, 'can_print': request.user.is_superuser}
    return render(request, 'results/admin_print_result.html', context)

# ===== ADMIN BROADSHEET - FINAL FIXED =====
@login_required
def admin_broadsheet(request, school_slug, class_id):
    school = get_object_or_404(School, slug=school_slug)
    if not is_school_admin_for_school(request, request.user, school):
        messages.error(request, f"Access Denied: You don't have permission to view {school.name}")
        return redirect('admin:index')

    student_class = get_object_or_404(StudentClass, id=class_id, school=school)
    session = request.GET.get('session', school.current_session) or "2025/2026"
    term = request.GET.get('term', school.current_term)
    if term not in ALL_TERMS:
        term = ALL_TERMS[0]
    view_mode = request.GET.get('view', 'detailed')

    students = Student.objects.filter(student_class=student_class).select_related('student_class').order_by('full_name')

    # FIX: GET SUBJECTS FROM StudentScore BECAUSE StudentSubject HAS NO 'session' FIELD
    subject_ids = StudentScore.objects.filter(
        student__student_class=student_class,
        session=session
    ).values_list('subject_id', flat=True).distinct()

    subjects = Subject.objects.filter(id__in=subject_ids, school=school).order_by('name')

    components = AssessmentComponent.objects.filter(school=school).order_by('order')
    MAX_TOTAL = 100.0
    logo_url = request.build_absolute_uri(school.logo.url) if school.logo else None
    broadsheet_data = []

    for student in students:
        # FIX: Only subjects this student has scores for in this session
        student_subject_ids = StudentScore.objects.filter(student=student, session=session).values_list('subject_id', flat=True)
        student_subjects = subjects.filter(id__in=student_subject_ids)

        row_data = {'student': student, 'subject_rows': [], 'cum_total_percent': 0.0, 'cum_average': 0.0, 'display_cum_total': '-', 'display_cum_avg': '-'}
        term_percents = []

        for subject in student_subjects:
            subject_row = {'subject': subject, 'cells': []}
            if term == "Third Term":
                t1_total = get_student_subject_total(student, subject, "First Term", session)
                t2_total = get_student_subject_total(student, subject, "Second Term", session)
                t1_percent = round((t1_total / MAX_TOTAL) * 100, 1) if t1_total > 0 else '-'
                t2_percent = round((t2_total / MAX_TOTAL) * 100, 1) if t2_total > 0 else '-'
                term_percents.extend([p for p in [t1_percent, t2_percent] if isinstance(p, (int, float))])
                subject_row['cells'].extend([t1_percent, t2_percent])

                t3_sum = 0
                for comp in components:
                    comp_score = get_component_score(student, subject, "Third Term", session, comp.name)
                    subject_row['cells'].append(comp_score if comp_score > 0 else '-')
                    if isinstance(comp_score, (int, float)): t3_sum += comp_score
                subject_row['cells'].append(t3_sum if t3_sum > 0 else '-')
                grade, _ = get_grade_and_remark(school, t3_sum) if t3_sum > 0 else ('-', '-')
                subject_row['cells'].append(grade)
                t3_percent = round((t3_sum / MAX_TOTAL) * 100, 1) if t3_sum > 0 else '-'
                if isinstance(t3_percent, (int, float)): term_percents.append(t3_percent)
            else:
                current = get_student_subject_total(student, subject, term, session)
                grade, _ = get_grade_and_remark(school, current) if current > 0 else ('-', '-')
                for comp in components:
                    comp_score = get_component_score(student, subject, term, session, comp.name)
                    subject_row['cells'].append(comp_score if comp_score > 0 else '-')
                subject_row['cells'].append(current if current > 0 else '-')
                subject_row['cells'].append(grade)
                if current > 0: term_percents.append(round((current / MAX_TOTAL) * 100, 1))

            row_data['subject_rows'].append(subject_row)

        valid_percents = [p for p in term_percents if isinstance(p, (int, float))]
        if valid_percents:
            row_data['cum_total_percent'] = round(sum(valid_percents), 1)
            row_data['cum_average'] = round(sum(valid_percents) / len(valid_percents), 1)
            row_data['display_cum_total'] = row_data['cum_total_percent']
            row_data['display_cum_avg'] = row_data['cum_average']

        broadsheet_data.append(row_data)

    broadsheet_data.sort(key=lambda x: x['cum_total_percent'], reverse=True)
    for i, row in enumerate(broadsheet_data): row['position'] = i + 1

    context = {
        'school': school, 'school_slug': school_slug, 'student_class': student_class,
        'subjects': subjects, 'components': components, 'broadsheet_data': broadsheet_data,
        'term': term, 'session': session, 'all_terms': ALL_TERMS, 'MAX_TOTAL': MAX_TOTAL,
        'logo_url': logo_url, 'can_print': request.user.is_superuser,
        'student_count': students.count(), 'view_mode': view_mode
    }
    return render(request, 'results/admin_broadsheet.html', context)

# ===== DOWNLOAD BROADSHEET PDF =====
@login_required
def download_broadsheet_pdf(request, school_slug, class_id):
    if not request.user.is_superuser:
        raise PermissionDenied
    school = get_object_or_404(School, slug=school_slug)
    term = request.GET.get('term', 'First Term')
    view_mode = 'summary'
    student_class = get_object_or_404(StudentClass, id=class_id, school=school)
    session = request.GET.get('session', school.current_session)
    subjects = Subject.objects.filter(school=school, student_class=student_class, studentsubject__session=session).distinct().order_by('name')
    components = AssessmentComponent.objects.filter(school=school).order_by('order')
    students = Student.objects.filter(student_class__school=school, student_class=student_class).order_by('full_name')
    MAX_TOTAL = 100.0
    logo_url = request.build_absolute_uri(school.logo.url) if school.logo else None
    broadsheet_data = []
    for student in students:
        student_subjects = subjects.filter(studentsubject__student=student)
        row_data = {'student': student, 'subject_rows': [], 'cum_total_percent': 0.0, 'cum_average': 0.0, 'display_cum_total': '-', 'display_cum_avg': '-'}
        term_percents = []
        for subject in student_subjects:
            subject_row = {'subject': subject, 'cells': []}
            if term == "Third Term":
                t1_total = get_student_subject_total(student, subject, "First Term", session)
                t2_total = get_student_subject_total(student, subject, "Second Term", session)
                t1_percent = round((t1_total / MAX_TOTAL) * 100, 1) if t1_total > 0 else '-'
                t2_percent = round((t2_total / MAX_TOTAL) * 100, 1) if t2_total > 0 else '-'
                term_percents.extend([p for p in [t1_percent, t2_percent] if isinstance(p, (int, float))])
                subject_row['cells'].extend([t1_percent, t2_percent])
                t3_sum = 0
                for comp in components:
                    comp_score = get_component_score(student, subject, "Third Term", session, comp.name)
                    subject_row['cells'].append(comp_score if comp_score > 0 else '-')
                    if isinstance(comp_score, (int, float)): t3_sum += comp_score
                subject_row['cells'].append(t3_sum if t3_sum > 0 else '-')
                grade, _ = get_grade_and_remark(school, t3_sum) if t3_sum > 0 else ('-', '-')
                subject_row['cells'].append(grade)
                t3_percent = round((t3_sum / MAX_TOTAL) * 100, 1) if t3_sum > 0 else '-'
                if isinstance(t3_percent, (int, float)): term_percents.append(t3_percent)
            else:
                current = get_student_subject_total(student, subject, term, session)
                grade, _ = get_grade_and_remark(school, current) if current > 0 else ('-', '-')
                for comp in components:
                    comp_score = get_component_score(student, subject, term, session, comp.name)
                    subject_row['cells'].append(comp_score if comp_score > 0 else '-')
                subject_row['cells'].append(current if current > 0 else '-')
                subject_row['cells'].append(grade)
                if current > 0: term_percents.append(round((current / MAX_TOTAL) * 100, 1))
            row_data['subject_rows'].append(subject_row)
        valid_percents = [p for p in term_percents if isinstance(p, (int, float))]
        if valid_percents:
            row_data['cum_total_percent'] = round(sum(valid_percents), 1)
            row_data['cum_average'] = round(sum(valid_percents) / len(valid_percents), 1)
            row_data['display_cum_total'] = row_data['cum_total_percent']
            row_data['display_cum_avg'] = row_data['cum_average']
        broadsheet_data.append(row_data)
    broadsheet_data.sort(key=lambda x: x['cum_total_percent'], reverse=True)
    for i, row in enumerate(broadsheet_data): row['position'] = i + 1
    context = {'school': school, 'school_slug': school_slug, 'student_class': student_class, 'term': term, 'session': session, 'subjects': subjects, 'components': components, 'broadsheet_data': broadsheet_data, 'MAX_TOTAL': MAX_TOTAL, 'logo_url': logo_url, 'view_mode': view_mode}
    template = get_template('results/admin_broadsheet.html')
    html = template.render(context)
    response = HttpResponse(content_type='application/pdf')
    filename = f"{student_class.name}_{student_class.arm}_{term}_{session}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    pisa_status = pisa.CreatePDF(html, dest=response, link_callback=link_callback)
    if pisa_status.err: return HttpResponse('We had some errors <pre>' + html + '</pre>')
    return response

# ===== STUDENT AUTH + CBT =====
@student_required
def student_tests(request, school_slug):
    school = get_object_or_404(School, slug=school_slug)
    student = get_student(request, school)
    tests = Test.objects.filter(test_class=student.student_class, school=school, is_active=True)
    test_list = []
    for test in tests:
        session, created = StudentTestSession.objects.get_or_create(student=student, test=test, defaults={'start_time': timezone.now()})
        test_list.append({'test': test, 'session': session, 'is_submitted': session.is_submitted})
    return render(request, 'results/student_test_list.html', {'test_list': test_list, 'school': school, 'student': student, 'school_slug': school_slug})

@student_required
def take_test(request, school_slug, session_id):
    school = get_object_or_404(School, slug=school_slug)
    session = get_object_or_404(StudentTestSession, id=session_id)
    test = session.test
    student = get_student(request, school)
    if session.student!= student or test.school!= school:
        messages.error(request, 'You are not authorized for this test')
        return redirect('results:student_tests', school_slug=school_slug)
    if session.is_submitted:
        messages.warning(request, 'You have already submitted this test')
        return redirect('results:student_tests', school_slug=school_slug)
    question_ids = list(test.questions.values_list('id', flat=True))
    if not question_ids:
        messages.error(request, 'No questions added to this test yet')
        return redirect('results:student_tests', school_slug=school_slug)
    current_q_num = int(request.GET.get('q', 1))
    if current_q_num < 1: current_q_num = 1
    if current_q_num > len(question_ids): current_q_num = len(question_ids)
    if request.method == "POST":
        action = request.POST.get('action')
        question_id = request.POST.get('question_id')
        answer = request.POST.get('answer')
        if answer and question_id:
            StudentAnswer.objects.update_or_create(session=session, question_id=question_id, defaults={'selected_answer': answer})
        if action == 'prev':
            current_q_num -= 1
        else:
            current_q_num += 1
        if current_q_num > len(question_ids):
            session.is_submitted = True
            session.end_time = timezone.now()
            score = 0
            for ans in session.answers.select_related('question'):
                if ans.selected_answer == ans.question.correct_answer:
                    score += ans.question.marks
            session.score = score
            session.save()
            total_possible = sum(q.marks for q in test.questions.all())
            component, _ = AssessmentComponent.objects.get_or_create(school=school, section=student.student_class.section, name="CBT", defaults={'max_score': total_possible, 'order': 99})
            StudentScore.objects.update_or_create(student=student, subject=test.subject, term=school.current_term, session=school.current_session, component=component, defaults={'score': session.score})
            messages.success(request, f'Test submitted! Your score: {session.score}/{total_possible}')
            return redirect('results:test_result', school_slug=school_slug, session_id=session.id)
        return redirect(f"{reverse('results:take_test', args=[school_slug, session.id])}?q={current_q_num}")
    question_id = question_ids[current_q_num - 1]
    question = get_object_or_404(Question, id=question_id)
    prev_answer_obj = StudentAnswer.objects.filter(session=session, question=question).first()
    answered_ids = list(StudentAnswer.objects.filter(session=session).values_list('question_id', flat=True))
    context = {'question': question, 'question_number': current_q_num, 'total_questions': len(question_ids), 'is_last': current_q_num == len(question_ids), 'session': session, 'school': school, 'school_slug': school_slug, 'test': test, 'prev_answer': prev_answer_obj.selected_answer if prev_answer_obj else None, 'question_ids': question_ids, 'answered_ids': answered_ids}
    return render(request, 'results/take_test.html', context)

@student_required
def test_result(request, school_slug, session_id):
    school = get_object_or_404(School, slug=school_slug)
    student = get_student(request, school)
    session = get_object_or_404(StudentTestSession, id=session_id, student=student, test__school=school)
    total_marks = sum(q.marks for q in session.test.questions.all())
    percentage = round((session.score / total_marks) * 100, 2) if total_marks > 0 else 0
    context = {'school': school, 'school_slug': school_slug, 'session': session, 'test': session.test, 'total_marks': total_marks, 'percentage': percentage}
    return render(request, 'results/test_result.html', context)

#====== RESET TEST =======
@staff_member_required
def reset_test(request, school_slug, session_id):
    school = get_object_or_404(School, slug=school_slug)
    session = get_object_or_404(StudentTestSession, id=session_id, test__school=school)
    if request.method == "POST":
        session.is_submitted = False
        session.score = 0
        session.start_time = timezone.now()
        session.end_time = None
        session.save()
        session.answers.all().delete()
        component = AssessmentComponent.objects.filter(school=school, name="CBT").first()
        if component:
            StudentScore.objects.filter(student=session.student, subject=session.test.subject, term=school.current_term, session=school.current_session, component=component).delete()
        messages.success(request, f"Test '{session.test.title}' has been reset for {session.student.full_name}.")
        return redirect('admin:results_studenttestsession_changelist')
    return render(request, 'admin/reset_test_confirm.html', {'session': session, 'school': school})


#=========== STUDENT DASHBOARD WITH TABS ===========
@student_required
def student_dashboard(request, school_slug):
    school = get_object_or_404(School, slug=school_slug)
    student = get_student(request, school)
    if student.student_class.school.id != school.id:
        messages.error(request, "Access Denied")
        return redirect('results:student_login', school_slug=school_slug)
    
    term = school.current_term
    session = school.current_session

    # 1. GET ALL APPROVED NOTES FOR THIS CLASS - NO TERM/SESSION FILTER
    notes = StudentNote.objects.filter(
        student_class=student.student_class,
        school=school,
        is_approved=True
    ).order_by('-uploaded_at')

    # 2. COUNT UNREAD NOTES FOR BELL
    unread_count = notes.filter(is_read=False).count()

    # 3. IF STUDENT CLICKS A NOTE, MARK IT AS READ
    note_id = request.GET.get('read')
    if note_id:
        StudentNote.objects.filter(id=note_id, student_class=student.student_class).update(is_read=True)
        return redirect('results:student_dashboard', school_slug=school_slug)

    # FIX: GET SUBJECTS THIS STUDENT OFFERS IN THIS CLASS
    student_subject_ids = StudentSubject.objects.filter(
        student=student,
        student_class=student.student_class
    ).values_list('subject_id', flat=True)
    
    subjects = Subject.objects.filter(
        school=school,
        id__in=student_subject_ids
    ).distinct().order_by('name')

    results_data = []
    total_score = 0
    for subject in subjects:
        term_total = get_student_subject_total(student, subject, term, session)
        if term_total > 0:
            grade, remark = get_grade_and_remark(school, term_total)
            results_data.append({
                'subject': subject.name,
                'total': term_total,
                'grade': grade,
                'remark': remark,
            })
            total_score += term_total

    average = round(total_score / len(results_data), 2) if results_data else 0

    # LINE 1: Get all active CA tests for this student's class
    active_ca_tests = CATest.objects.filter(student_class=student.student_class, school=school, is_active=True, status='approved')

    # LINE 2: Get IDs of CAs this student has already submitted
    submitted_ca_ids = StudentCASession.objects.filter(
        student=student,
        is_submitted=True,
        ca_test__in=active_ca_tests
    ).values_list('ca_test_id', flat=True)

    context = {
        'school': school,
        'school_slug': school_slug,
        'student': student,
        'notes': notes,
        'unread_count': unread_count,
        'results_data': results_data,
        'term': term,
        'session': session,
        'average': average,
        'active_ca_tests': active_ca_tests,
        'submitted_ca_ids': list(submitted_ca_ids),
    }
    return render(request, 'results/student_dashboard.html', context)

# ===== REPORT CARD - DETAILED LANDSCAPE VIEW =====
@login_required(login_url='login')
@staff_member_required
def report_card(request, school_slug, student_id, term):
    school = get_object_or_404(School, slug=school_slug)
    student = get_object_or_404(Student, id=student_id, student_class__school=school)
    student_class = student.student_class
    session = school.current_session

    components = AssessmentComponent.objects.filter(school=school).order_by('order')
    # FIX: ONLY SUBJECTS STUDENT OFFERS
    subjects = Subject.objects.filter(
        school=school,
        student_class=student_class,
        studentsubject__student=student,
        studentsubject__session=session
    ).distinct().order_by('name')
    grades = GradeScale.objects.filter(school=school)

    subjects_data = []
    total_score_sum = 0

    for subject in subjects:
        scores = StudentScore.objects.filter(student=student, subject=subject, term=term, session=session)
        component_scores = []
        exam_score = 0
        total = 0

        for comp in components:
            score_obj = scores.filter(component=comp).first()
            score_val = float(score_obj.score) if score_obj else 0
            component_scores.append(score_val)
            total += score_val
            if 'EXAM' in comp.name.upper():
                exam_score = score_val

        grade_obj = grades.filter(min_score__lte=total, max_score__gte=total).first()
        grade = grade_obj.grade if grade_obj else '-'
        remark = grade_obj.remark if grade_obj else '-'

        cum_percent = '-'
        if term == 'Third Term':
            cum_total = 0
            divisor = TERM_ORDER[term]
            for t in ALL_TERMS[:divisor]:
                t_scores = StudentScore.objects.filter(student=student, subject=subject, term=t, session=session)
                cum_total += sum([float(s.score) for s in t_scores])
            max_total = sum([c.max_score for c in components]) * divisor
            if max_total > 0:
                cum_percent = round((cum_total / max_total) * 100, 1)

        first_term_total = second_term_total = '-'
        if term == 'Third Term':
            f_scores = StudentScore.objects.filter(student=student, subject=subject, term='First Term', session=session)
            s_scores = StudentScore.objects.filter(student=student, subject=subject, term='Second Term', session=session)
            first_term_total = sum([float(s.score) for s in f_scores])
            second_term_total = sum([float(s.score) for s in s_scores])

        subjects_data.append({
            'name': subject.name,
            'component_scores': component_scores,
            'exam': exam_score,
            'total': total,
            'grade': grade,
            'remark': remark,
            'cum_percent': cum_percent,
            'first_term_total': first_term_total,
            'second_term_total': second_term_total,
        })
        total_score_sum += total

    total_score = total_score_sum
    average = round(total_score / len(subjects) if subjects else 0, 2)
    overall_grade_obj = grades.filter(min_score__lte=average, max_score__gte=average).first()
    overall_grade = overall_grade_obj.grade if overall_grade_obj else '-'

    position = 1
    total_students = Student.objects.filter(student_class=student_class).count()

    attendance = Attendance.objects.filter(student=student, term=term, session=session, status='Present').count()
    total_days = Attendance.objects.filter(student_class=student_class, term=term, session=session).values('date').distinct().count()

    context = {
        'school': school,
        'logo_url': school.logo.url if school.logo else None,
        'principal_signature_url': school.principal_signature.url if school.principal_signature else None,
        'student': student,
        'student_class': student_class,
        'term': term,
        'session': session,
        'components': components,
        'subjects_data': subjects_data,
        'total_score': total_score,
        'average': average,
        'overall_grade': overall_grade,
        'position': position,
        'total_students': total_students,
        'attendance': attendance,
        'total_days': total_days,
        'resumption_date': school.next_term_resumption_date,
        'teacher_comment': '',
        'principal_comment': 'Well Done. Keep it up.',
    }
    return render(request, 'results/report_card.html', context)

#=========== LANDING PAGE ===========
def landing_page(request, school_slug):
    school = get_object_or_404(School, slug=school_slug)
    return render(request, 'results/landing.html', {'school': school})

#=========== SCHOOL SPECIFIC LOGINS ===========
def admin_login(request, school_slug):
    """School Admin Login - redirects to django admin with school in session"""
    school = get_object_or_404(School, slug=school_slug)
    request.session['school_slug'] = school_slug
    request.session.modified = True
    return redirect('/admin/')

#======= PARENT LOGIN ========
def parent_login(request, school_slug):
    """School Parent Login - 3 times usage"""
    school = get_object_or_404(School, slug=school_slug)

    if request.method == 'POST':
        admission_no = request.POST.get('student_id', '').strip()
        access_code = request.POST.get('access_code', '').strip()

        student = Student.objects.filter(admission_no=admission_no, student_class__school=school).first()
        scratchcard = ScratchCard.objects.filter(pin=access_code, school=school).first()

        if not student:
            messages.error(request, f'❌ Admission No "{admission_no}" not found in {school.name}')
        elif not scratchcard:
            messages.error(request, f'❌ PIN "{access_code}" not found for {school.name}')
        elif scratchcard.usage_count >= scratchcard.max_usage:
            scratchcard.used = True
            scratchcard.save()
            used_by = scratchcard.used_by_student.full_name if scratchcard.used_by_student else "Someone"
            messages.error(request, f'❌ This PIN has been used {scratchcard.max_usage} times already (last by {used_by}) and is now expired.')
        else:
            scratchcard.usage_count += 1
            scratchcard.used_by_student = student
            scratchcard.date_used = timezone.now()
            
            if scratchcard.usage_count >= scratchcard.max_usage:
                scratchcard.used = True
            
            scratchcard.save()

            request.session['student_id'] = student.id
            request.session['school_id'] = school.id
            
            remaining = scratchcard.max_usage - scratchcard.usage_count
            if remaining > 0:
                messages.success(request, f'Login successful. Welcome {student.full_name}. PIN can still be used {remaining} more time(s).')
            else:
                messages.success(request, f'Login successful. Welcome {student.full_name}. PIN has now expired after {scratchcard.max_usage} uses.')
            
            return redirect('results:parent_print_result', school_slug=school.slug, student_id=student.id)

    return render(request, 'results/parent_login.html', {'school': school})

def portal_login(request, school_slug):
    school = get_object_or_404(School, slug=school_slug)
    request.session['school_slug'] = school_slug
    request.session.modified = True
    return render(request, 'results/portal_login.html', {'school': school})

#======= PARENT TRANSCRIPT LOGIN =========
def parent_transcript_login(request, school_slug):
    school = get_object_or_404(School, slug=school_slug)

    if request.method == "POST":
        admission_no = request.POST.get('admission_no')
        pin = request.POST.get('pin')
        student = Student.objects.filter(student_class__school=school, admission_no=admission_no, transcript_pin=pin).first()

        if student:
            request.session['parent_student_id'] = student.id
            return redirect('results:view_transcript', school_slug=school_slug, student_id=student.id)
        else:
            messages.error(request, "Invalid Admission No or PIN")

    return render(request, 'results/parent_transcript_login.html', {'school': school})

#===== STUDENT NOTE ========
from django.shortcuts import get_object_or_404, redirect, render
from .models import School, StudentNote 

@student_required
def student_notes(request, school_slug):
    school = get_object_or_404(School, slug=school_slug)
    student = get_student(request)
    student_class = student.student_class

    notes = StudentNote.objects.filter(
        school=school,
        student_class=student_class,
        term=school.current_term,
        session=school.current_session,
        is_approved=True
    ).order_by('-uploaded_at')

    return render(request, 'results/student_notes.html', {
        'school': school, 
        'student': student, 
        'notes': notes,
        'term': school.current_term,
        'session': school.current_session,
    })

@student_required
def student_note_detail(request, school_slug, note_id):
    school = get_object_or_404(School, slug=school_slug)
    student = get_student(request)

    note = get_object_or_404(
        StudentNote, 
        id=note_id, 
        school=school, 
        student_class=student.student_class
    )
    
    # Auto mark as read when viewed
    if not note.is_read:
        note.is_read = True
        note.save()

    return render(request, 'results/student_note_detail.html', {
        'school': school,
        'student': student,
        'note': note,
        'term': school.current_term,
        'session': school.current_session,
    })

#======== STUDENT TRANSCRIPT =========
def student_transcript(request, school_slug, student_id):
    school = get_object_or_404(School, slug=school_slug)
    student = get_object_or_404(Student, id=student_id)

    if student.student_class.school!= school:
        return HttpResponseForbidden("This student does not belong to this school")

    grades = GradeScale.objects.filter(school=school)

    # ✅ FIXED - Use StudentScore and correct select_related
    all_scores = StudentScore.objects.filter(
        student=student
    ).select_related('subject', 'component', 'student__student_class')

    grouped_data = defaultdict(list)
    for score in all_scores:
        session = score.session
        # ✅ FIXED - Subject has no student_class, use student's class
        class_name = student.student_class.name
        key = f"{session} - {class_name}"
        grouped_data[key].append(score)

    transcript_sections = []
    for group_key, scores in grouped_data.items():
        session, class_name = group_key.split(' - ')
        # ✅ FIXED - Subject filter no longer uses student_class__name
        subjects = Subject.objects.filter(school=school).order_by('name').distinct()
        class_table = []
        for subject in subjects:
            term_scores = {}
            total_sum = 0
            count = 0
            for term in ALL_TERMS:
                total_for_term = sum(float(s.score) for s in scores if s.subject == subject and s.term == term)
                term_scores[term] = round(total_for_term, 2) if total_for_term > 0 else "-"
                if total_for_term > 0:
                    total_sum += total_for_term
                    count += 1
            cum_avg = round(total_sum / count, 2) if count > 0 else "-"
            grade, remark = "-", "-"
            if cum_avg!= "-":
                grade_obj = grades.filter(min_score__lte=cum_avg, max_score__gte=cum_avg).first()
                if grade_obj:
                    grade, remark = grade_obj.grade, grade_obj.remark
            # Only add subject if student has scores for it
            if any(s.subject == subject for s in scores):
                class_table.append({'subject': subject.name, 'terms': term_scores, 'cum_avg': cum_avg, 'grade': grade, 'remark': remark})

        transcript_sections.append({'session_class': group_key, 'table': class_table})

    context = {
        'school': school,
        'student': student,
        'transcript_sections': transcript_sections,
        'all_terms': ALL_TERMS,
    }
    return render(request, 'results/transcript.html', context)

#======= VIEW TRANSCRIPT ========
def view_transcript(request, school_slug, student_id):
    school = get_object_or_404(School, slug=school_slug)
    student = get_object_or_404(Student, id=student_id, student_class__school=school)
    return render(request, 'results/transcript.html', {'school': school, 'student': student})

#===== BULK ADD SUBJECT =======
@login_required
def bulk_allocate_subjects(request, school_slug):
    school = get_object_or_404(School, slug=school_slug)
    if not is_school_admin_for_school(request, request.user, school):
        raise PermissionDenied

    selected_class_name = None
    selected_arm = None
    students = []
    subjects = []
    session = request.GET.get('session', school.current_session)

    # Load students + subjects when class is selected
    if request.GET.get('class_name'):
        selected_class_name = request.GET.get('class_name')
        selected_arm = request.GET.get('arm') # can be empty = all arms

        # Base queryset
        students_qs = Student.objects.filter(
            student_class__name=selected_class_name, 
            student_class__school=school
        )

        # If arm is selected, filter further
        if selected_arm:
            students_qs = students_qs.filter(student_class__arm=selected_arm)

        students = students_qs.select_related('student_class').order_by('student_class__arm', 'full_name')
        subjects = Subject.objects.filter(school=school).order_by('name')

    if request.method == 'POST':
        class_name = request.POST.get('class_name')
        arm = request.POST.get('arm')
        subject_ids = request.POST.getlist('subjects')  
        student_ids = request.POST.getlist('students')  

        subject_objs = Subject.objects.filter(id__in=subject_ids, school=school)
        student_objs = Student.objects.filter(id__in=student_ids, student_class__school=school)

        created_count = 0
        for student in student_objs:
            for subject in subject_objs:
                obj, created = StudentSubject.objects.get_or_create(
                    student=student,
                    subject=subject,
                    student_class=student.student_class
                )
                if created:
                    created_count += 1
        
        messages.success(request, f"{created_count} subject allocations created for {len(student_objs)} students")
        return redirect('bulk_allocate_subjects', school_slug=school.slug)

    # For dropdowns
    class_names = StudentClass.objects.filter(school=school).values_list('name', flat=True).distinct().order_by('name')
    arms = []
    if selected_class_name:
        arms = StudentClass.objects.filter(school=school, name=selected_class_name).values_list('arm', flat=True).distinct()

    context = {
        'school': school,
        'school_slug': school_slug,
        'class_names': class_names,
        'arms': arms,
        'selected_class_name': selected_class_name,
        'selected_arm': selected_arm,
        'students': students,
        'subjects': subjects,
        'session_choices': SESSION_CHOICES,
        'selected_session': session,
    }
    return render(request, 'results/bulk_allocate_subjects.html', context)


#===== ID CARD - STUDENT + TEACHER - FINAL FIXED ========
import qrcode
import base64
from io import BytesIO
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

def _qr_b64(url):
    qr = qrcode.QRCode(box_size=4, border=1)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"

def _get_photo_url(obj):
    # Works for both Student and Teacher - PASSPORT ONLY
    try:
        if hasattr(obj, 'passport') and obj.passport:
            return obj.passport.url
        if hasattr(obj, 'photo') and obj.photo:
            return obj.photo.url
        if hasattr(obj, 'image') and obj.image:
            return obj.image.url
    except:
        pass
    return None

def _get_signature_url(obj):
    try:
        if hasattr(obj, 'signature') and obj.signature:
            return obj.signature.url
    except:
        pass
    return None

# ----- STUDENT -----
def print_id_cards(request, school_slug):
    from .models import School, Student, StudentClass
    school = get_object_or_404(School, slug=school_slug)
    
    layout = request.GET.get('layout', 'landscape').lower()
    if layout not in ['landscape', 'portrait', 'back', 'portrait_back']:
        layout = 'landscape'
    
    class_id = request.GET.get('class_id')
    student_id = request.GET.get('student_id')
    ids = request.GET.get('ids')

    qs = Student.objects.filter(student_class__school=school).select_related('student_class').order_by('full_name')
    if student_id:
        qs = qs.filter(id=student_id)
    elif ids:
        try:
            id_list = [int(i) for i in ids.split(',') if i.strip().isdigit()]
            qs = qs.filter(id__in=id_list)
        except:
            pass
    elif class_id and class_id.isdigit():
        qs = qs.filter(student_class_id=class_id)

    students = []
    for s in qs:
        verify_url = request.build_absolute_uri(reverse('results:verify_student_id', args=[school_slug, s.admission_no]))
        s.qr_code = _qr_b64(verify_url)
        s.photo_url = _get_photo_url(s)
        students.append(s)

    classes = StudentClass.objects.filter(school=school).order_by('name')

    return render(request, 'results/id_cards.html', {
        'school': school,
        'students': students,
        'classes': classes,
        'selected_class_id': int(class_id) if class_id and class_id.isdigit() else None,
        'layout': layout,
        'primary_color': getattr(school, 'primary_color', None) or '#800020',
        'secondary_color': getattr(school, 'secondary_color', None) or '#FFD700',
    })

def verify_student_id(request, school_slug, admission_no):
    from .models import School, Student
    school = get_object_or_404(School, slug=school_slug)
    student = get_object_or_404(Student, admission_no=admission_no, student_class__school=school)
    return render(request, 'results/verify_id.html', {
        'school': school, 'student': student,
        'primary_color': getattr(school, 'primary_color', None) or '#800020',
    })

# ----- TEACHER - SAAS SAFE / 4 LAYOUTS - FIXED FOR PASSPORT + SIGNATURE -----
def print_teacher_id_cards(request, school_slug):
    from .models import School, Teacher
    school = get_object_or_404(School, slug=school_slug)
    
    layout = request.GET.get('layout', 'landscape').lower()
    if layout not in ['landscape', 'portrait', 'back', 'portrait_back']:
        layout = 'landscape'

    qs = Teacher.objects.filter(school=school).order_by('full_name')

    teacher_id = request.GET.get('teacher_id')
    if teacher_id and teacher_id.isdigit():
        qs = qs.filter(id=int(teacher_id))

    teachers = []
    for t in qs:
        t.display_id = f"{school.slug[:4].upper()}/{t.id:04d}"
        t.qr_code = _qr_b64(
            request.build_absolute_uri(f"/{school_slug}/teacher-id-cards/verify/{t.id}/")
        )
        t.photo_url = _get_photo_url(t)
        t.signature_url = _get_signature_url(t)

        if not getattr(t, 'full_name', None):
            if getattr(t, 'user', None):
                try:
                    t.full_name = t.user.get_full_name() or t.user.username
                except Exception:
                    t.full_name = t.user.username
            else:
                t.full_name = f"Teacher {t.id}"

        teachers.append(t)

    principal_sig = None
    if hasattr(school, 'principal_signature') and school.principal_signature:
        try:
            principal_sig = school.principal_signature.url
        except:
            pass

    return render(request, 'results/teacher_id_cards.html', {
        'school': school,
        'teachers': teachers,
        'layout': layout,
        'principal_signature_url': principal_sig,
        'primary_color': getattr(school, 'primary_color', None) or '#800020',
        'secondary_color': getattr(school, 'secondary_color', None) or '#FFD700',
    })

def verify_teacher_id(request, school_slug, staff_id):
    from .models import School, Teacher
    school = get_object_or_404(School, slug=school_slug)
    teacher = get_object_or_404(Teacher, school=school, id=staff_id)
    return render(request, 'results/verify_teacher.html', {
        'school': school,
        'teacher': teacher,
        'primary_color': getattr(school, 'primary_color', None) or '#800020',
    })

# ===== ONLINE ADMISSION - SAAS PAYSTACK VERSION =====
import time
import requests
from django.utils import timezone

def admission_apply(request, school_slug):
    school = get_object_or_404(School, slug=school_slug)
    if request.method == 'POST':
        form = AdmissionForm(request.POST, request.FILES)
        if form.is_valid():
            application = form.save(commit=False)
            application.school = school
            application.amount_paid = school.admission_form_fee
            application.paystack_ref = f"ADM-{school.id}-{int(time.time())}"
            
            # CASE 1: FREE or NO PAYSTACK KEYS SET
            if not school.paystack_secret_key or float(school.admission_form_fee) == 0:
                application.is_paid = True
                application.status = 'Paid'
                application.payment_date = timezone.now()
                application.save()
                messages.success(request, "Application submitted successfully!")
                return redirect('results:admission_success', school_slug=school_slug, pk=application.pk)
            
            # CASE 2: PAID - INIT PAYSTACK WITH SCHOOL'S OWN KEY
            application.is_paid = False
            application.status = 'Pending'
            application.save()

            headers = {
                "Authorization": f"Bearer {school.paystack_secret_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "email": application.parent_email or f"{application.parent_phone}@admission.com",
                "amount": int(float(school.admission_form_fee) * 100), # Paystack uses kobo
                "reference": application.paystack_ref,
                "callback_url": request.build_absolute_uri(
                    reverse('results:admission_verify_payment', args=[school_slug, application.pk])
                ),
                "metadata": {"school": school.name, "applicant": application.full_name}
            }
            try:
                r = requests.post("https://api.paystack.co/transaction/initialize", headers=headers, json=payload, timeout=20)
                resp = r.json()
                if resp.get('status'):
                    return redirect(resp['data']['authorization_url'])
                else:
                    messages.error(request, f"Paystack Error: {resp.get('message')}")
            except Exception as e:
                messages.error(request, f"Payment connection failed: {e}")
                # fallback - save as unpaid but allow retry
    else:
        form = AdmissionForm()
    return render(request, 'results/admission_form.html', {'school': school, 'form': form, 'fee': school.admission_form_fee})

def admission_verify_payment(request, school_slug, pk):
    school = get_object_or_404(School, slug=school_slug)
    application = get_object_or_404(AdmissionApplication, pk=pk, school=school)

    headers = {"Authorization": f"Bearer {school.paystack_secret_key}"}
    try:
        r = requests.get(f"https://api.paystack.co/transaction/verify/{application.paystack_ref}", headers=headers, timeout=20)
        data = r.json().get('data', {})
        if data.get('status') == 'success':
            application.is_paid = True
            application.status = 'Paid'
            application.payment_date = timezone.now()
            application.amount_paid = float(data.get('amount', 0)) / 100
            application.save()
            messages.success(request, "Payment verified! Application received.")
            return redirect('results:admission_success', school_slug=school_slug, pk=application.pk)
    except Exception as e:
        messages.error(request, f"Verification error: {e}")
    
    messages.error(request, "Payment not verified. Please try again or contact school.")
    return redirect('results:admission_apply', school_slug=school_slug)

def admission_success(request, school_slug, pk):
    school = get_object_or_404(School, slug=school_slug)
    application = get_object_or_404(AdmissionApplication, pk=pk, school=school)
    return render(request, 'results/admission_success.html', {'school': school, 'application': application})

#========= LESSON PLAN =========
@login_required
def teacher_lesson_plan(request, school_slug=None):
    from .models import School, Teacher, LessonPlan, StudentClass, Subject
    
    school = School.objects.filter(slug=school_slug).first() if school_slug else getattr(request, 'school', None)
    if not school:
        school = School.objects.first()

    teacher_profile = Teacher.objects.filter(user=request.user).first()
    classes = StudentClass.objects.filter(school=school) if school else StudentClass.objects.all()
    subjects = Subject.objects.filter(school=school) if school else Subject.objects.all()
    
    # Teacher filter if teacher has assigned classes
    if teacher_profile and teacher_profile.classes.exists():
        classes = teacher_profile.classes.all()
        subjects = teacher_profile.subjects.all() if teacher_profile.subjects.exists() else subjects

    if request.method == 'POST':
        class_id = request.POST.get('student_class')
        subject_id = request.POST.get('subject')
        
        # Convert IDs to real names
        try:
            class_obj = StudentClass.objects.get(id=class_id)
            class_name = f"{class_obj.name} {class_obj.arm or ''}".strip() # JSS1 A
        except:
            class_name = class_id
            
        try:
            subject_obj = Subject.objects.get(id=subject_id)
            subject_name = subject_obj.name
        except:
            subject_name = subject_id

        LessonPlan.objects.create(
            school=school,
            teacher=request.user,
            student_class=class_name,
            subject=subject_name,
            week=request.POST.get('week'),
            topic=request.POST.get('topic'),
            objectives=request.POST.get('objectives'),
            activities=request.POST.get('activities'),
            materials=request.POST.get('materials'),
            assignment=request.POST.get('assignment'),
        )
        from django.contrib import messages
        messages.success(request, f"✅ Lesson Plan saved!")
        return redirect('results:teacher_lesson_plan', school_slug=school.slug)

    plans = LessonPlan.objects.filter(school=school, teacher=request.user).order_by('-created_at')

    return render(request, 'results/teacher_lesson_plan.html', {
        'school': school,
        'classes': classes,
        'subjects': subjects,
        'plans': plans,
        'primary_color': getattr(school, 'primary_color', '#7a0c2e') if school else '#7a0c2e'
    })

# === PSYCHOMOTOR - CLASS TEACHER ONLY ===
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

@login_required(login_url='results:school_teacher_login')
@teacher_required
def psychomotor_class_list(request, school_slug):
    school = get_object_or_404(School, slug=school_slug)
    teacher = get_object_or_404(Teacher, user=request.user, school=school)
    
    # ONLY classes where this teacher is the class_teacher
    classes = StudentClass.objects.filter(school=school, class_teacher=teacher)
    
    if not classes.exists() and not request.user.is_superuser:
        messages.error(request, "Access Denied: Only Class Teachers can rate psychomotor. You are not assigned as a Class Teacher for any class.")
        return redirect('results:teacher_dashboard', school_slug=school_slug)
    
    # Super admin sees all
    if request.user.is_superuser:
        classes = StudentClass.objects.filter(school=school)
        
    return render(request, 'results/psychomotor_class_list.html', {'school': school, 'classes': classes})

@login_required(login_url='results:school_teacher_login')
@teacher_required
def psychomotor_student_list(request, school_slug, class_id):
    school = get_object_or_404(School, slug=school_slug)
    teacher = get_object_or_404(Teacher, user=request.user, school=school)
    student_class = get_object_or_404(StudentClass, id=class_id, school=school)
    
    # SECURITY CHECK
    if student_class.class_teacher != teacher and not request.user.is_superuser:
        raise PermissionDenied("Only the Class Teacher of this class can access psychomotor ratings")
    
    students = Student.objects.filter(student_class=student_class, school=school).order_by('full_name')
    term = request.GET.get('term', school.current_term)
    session = request.GET.get('session', school.current_session)
    
    return render(request, 'results/psychomotor_student_list.html', {
        'school': school, 'class_obj': student_class, 'students': students, 'term': term, 'session': session
    })

@login_required(login_url='results:school_teacher_login')
@teacher_required
def rate_psychomotor(request, school_slug, student_id):
    school = get_object_or_404(School, slug=school_slug)
    teacher = get_object_or_404(Teacher, user=request.user, school=school)
    student = get_object_or_404(Student, id=student_id, school=school)
    
    # SECURITY CHECK
    if student.student_class.class_teacher != teacher and not request.user.is_superuser:
        raise PermissionDenied("Only the Class Teacher can rate psychomotor for this student")
    
    term = request.GET.get('term', school.current_term)
    session = request.GET.get('session', school.current_session)
    
    obj, created = Psychomotor.objects.get_or_create(
        student=student, term=term, session=session,
        defaults={f:0 for f in ['punctuality','neatness','honesty','politeness','attentiveness','handwriting','games_sports','handling_tools','drawing','leadership']}
    )
    if request.method == 'POST':
        for field in ['punctuality','neatness','honesty','politeness','attentiveness','handwriting','games_sports','handling_tools','drawing','leadership']:
            setattr(obj, field, int(request.POST.get(field, 0) or 0))
        obj.save()
        messages.success(request, f"Saved for {student.full_name}")
        next_student = Student.objects.filter(student_class=student.student_class, school=school, id__gt=student.id).order_by('id').first()
        if next_student:
            return redirect(f"{reverse('results:rate_psychomotor', kwargs={'school_slug':school_slug,'student_id':next_student.id})}?term={term}&session={session}")
        return redirect('results:psychomotor_student_list', school_slug=school_slug, class_id=student.student_class.id)

    return render(request, 'results/rate_psychomotor.html', {
        'school': school, 'student': student, 'obj': obj, 'term': term, 'session': session
    })