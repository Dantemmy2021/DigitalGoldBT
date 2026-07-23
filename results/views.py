from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django import template
from .models import Subject, Score, Student

# Template filter so we can do scores_dict|get_item:student.id in html
register = template.Library()

@register.filter
def get_item(dictionary, key):
    if dictionary is None:
        return None
    return dictionary.get(key)

# HELPER FUNCTIONS FOR GRADE AND REMARK
def get_grade(score):
    if score >= 70: return "A1"
    elif score >= 60: return "B2"
    elif score >= 50: return "B3"
    elif score >= 45: return "C4"
    elif score >= 40: return "C5"
    elif score >= 35: return "C6"
    elif score >= 30: return "D7"
    elif score >= 25: return "E8"
    else: return "F9"

def get_remark(score):
    if score >= 70: return "Excellent"
    elif score >= 60: return "Very Good"
    elif score >= 50: return "Good"
    elif score >= 40: return "Credit"
    elif score >= 35: return "Pass"
    else: return "Fail"

@login_required
def home_redirect(request):
    if request.user.is_staff:
        return redirect('/admin/')
    else:
        return redirect('/teacher/')

@login_required
def teacher_dashboard(request):
    subjects = Subject.objects.filter(teachers=request.user)
    students = Student.objects.filter(student_class__in=[s.student_class for s in subjects]).distinct()
    context = {'subjects': subjects, 'students': students}
    return render(request, 'results/teacher_dashboard.html', context)

@login_required
def enter_scores(request, subject_id):
    subject = get_object_or_404(Subject, id=subject_id)
    if request.user not in subject.teachers.all() and not request.user.is_superuser:
        messages.error(request, "You are not assigned to this subject")
        return redirect('results:teacher_dashboard')

    students = Student.objects.filter(student_class=subject.student_class)
    TERM = 'Third Term'
    SESSION = '2025/2026'
    existing_scores = Score.objects.filter(subject=subject, term=TERM, session=SESSION)
    scores_dict = {score.student_id: score for score in existing_scores}

    if request.method == 'POST':
        has_error = False
        saved_count = 0
        for student in students:
            try:
                ca1 = int(request.POST.get(f'ca1_{student.id}', 0) or 0)
                ca2 = int(request.POST.get(f'ca2_{student.id}', 0) or 0)
                project = int(request.POST.get(f'project_{student.id}', 0) or 0)
                assignment = int(request.POST.get(f'assignment_{student.id}', 0) or 0)
                exam = int(request.POST.get(f'exam_{student.id}', 0) or 0)
                if ca1 == 0 and ca2 == 0 and project == 0 and assignment == 0 and exam == 0: continue
                if ca1 > 10 or ca2 > 10 or project > 10 or assignment > 10:
                    messages.error(request, f"{student.full_name}: CA1, CA2, Project, Assignment cannot be more than 10")
                    has_error = True; break
                if exam > 60:
                    messages.error(request, f"{student.full_name}: Exam cannot be more than 60")
                    has_error = True; break
                total = ca1 + ca2 + project + assignment + exam
                if total > 100:
                    messages.error(request, f"{student.full_name}: Total cannot exceed 100. Current total is {total}")
                    has_error = True; break
                Score.objects.update_or_create(student=student, subject=subject, term=TERM, session=SESSION,
                    defaults={'ca1': ca1, 'ca2': ca2, 'project': project, 'assignment': assignment, 'exam': exam})
                saved_count += 1
            except ValueError:
                messages.error(request, f"{student.full_name}: Please enter valid numbers only")
                has_error = True; break
        if not has_error and saved_count > 0:
            messages.success(request, f"Scores saved for {saved_count} students in {subject.name}")
        elif not has_error and saved_count == 0:
            messages.info(request, "No scores were entered")
        return redirect('results:enter_scores', subject_id=subject.id)

    context = {'subject': subject, 'students': students, 'scores_dict': scores_dict}
    return render(request, 'results/enter_scores.html', context)

@login_required
def print_result(request, student_id):
    student = get_object_or_404(Student, id=student_id)
    subjects = Subject.objects.filter(teachers=request.user)
    my_classes = [s.student_class for s in subjects]
    if not request.user.is_superuser and student.student_class not in my_classes:
        messages.error(request, "You can only print results for students in your class")
        return redirect('results:teacher_dashboard')
    
    TERM = 'Third Term'
    SESSION = '2025/2026'
    ALL_TERMS = ['First Term', 'Second Term', 'Third Term']
    current_term_scores = Score.objects.filter(student=student, term=TERM, session=SESSION).select_related('subject')
    term_total = 0
    for score in current_term_scores:
        score.total = score.ca1 + score.ca2 + score.project + score.assignment + score.exam
        term_total += score.total
    cumulative_data = []
    session_average = 0
    if TERM == 'Third Term':
        for t in ALL_TERMS:
            term_scores = Score.objects.filter(student=student, term=t, session=SESSION)
            term_sum = sum(s.ca1 + s.ca2 + s.project + s.assignment + s.exam for s in term_scores)
            cumulative_data.append({'term': t, 'total': term_sum})
        if cumulative_data:
            session_total = sum(item['total'] for item in cumulative_data)
            session_average = round(session_total / 3, 2)
    context = {'student': student, 'scores': current_term_scores, 'term': TERM, 'session': SESSION, 'term_total': term_total, 'cumulative_data': cumulative_data, 'session_average': session_average}
    return render(request, 'results/print_result.html', context)

@staff_member_required
def admin_print_student(request, student_id):
    student = get_object_or_404(Student, id=student_id)
    TERM = request.GET.get('term', 'First Term') 
    SESSION = '2025/2026'
    ALL_TERMS = ['First Term', 'Second Term', 'Third Term']
    if TERM not in ALL_TERMS: TERM = 'First Term'

    scores = Score.objects.filter(student=student, term=TERM, session=SESSION).select_related('subject')
    results_data = []
    term_total = 0
    for score in scores:
        score_total = score.ca1 + score.ca2 + score.project + score.assignment + score.exam
        term_total += score_total
        results_data.append({'subject': score.subject.name, 'ca1': score.ca1, 'ca2': score.ca2, 'project': score.project, 'assignment': score.assignment, 'exam': score.exam, 'total': score_total, 'grade': get_grade(score_total), 'remark': get_remark(score_total)})
    
    average = round(term_total / len(results_data), 2) if len(results_data) > 0 else 0
    current_term_index = ALL_TERMS.index(TERM)
    joined_index = ALL_TERMS.index(student.joined_term)
    terms_to_calculate = ALL_TERMS[joined_index:current_term_index + 1]
    divisor = len(terms_to_calculate)
    cumulative_total = 0
    for t in terms_to_calculate:
        t_scores = Score.objects.filter(student=student, term=t, session=SESSION)
        cumulative_total += sum(s.ca1 + s.ca2 + s.project + s.assignment + s.exam for s in t_scores)
    cumulative_avg = round(cumulative_total / divisor, 2) if divisor > 0 else 0

    all_students_in_class = Student.objects.filter(student_class=student.student_class)
    class_totals = []
    for s in all_students_in_class:
        s_scores = Score.objects.filter(student=s, term=TERM, session=SESSION)
        s_total = sum(sc.ca1 + sc.ca2 + sc.project + sc.assignment + sc.exam for sc in s_scores)
        class_totals.append({'student': s, 'total': s_total})
    class_totals.sort(key=lambda x: x['total'], reverse=True)
    position = 1
    for i, data in enumerate(class_totals):
        if data['student'].id == student.id: position = i + 1; break

    context = {'student': student, 'results_data': results_data, 'total_score': term_total, 'average': average, 'cumulative_avg': cumulative_avg, 'divisor': divisor, 'position': f"{position} out of {len(all_students_in_class)}", 'term': TERM, 'session': SESSION, 'all_terms': ALL_TERMS}
    return render(request, 'results/admin_print_student.html', context)

# ========= ADMIN BROADSHEET: WHOLE CLASS =========
@staff_member_required
def admin_broadsheet(request, class_id):
    student_class = get_object_or_404(SchoolClass, id=class_id)
    TERM = request.GET.get('term', 'First Term') 
    SESSION = '2025/2026'
    ALL_TERMS = ['First Term', 'Second Term', 'Third Term']
    if TERM not in ALL_TERMS: TERM = 'First Term'

    students = Student.objects.filter(student_class=student_class).order_by('full_name')
    subjects = Subject.objects.filter(student_class=student_class).order_by('name')

    broadsheet_data = []
    for student in students:
        student_row = {'student': student, 'scores': [], 'total': 0}
        student_total = 0
        for subject in subjects:
            score = Score.objects.filter(student=student, subject=subject, term=TERM, session=SESSION).first()
            if score:
                score_total = score.ca1 + score.ca2 + score.project + score.assignment + score.exam
                student_total += score_total
                student_row['scores'].append({'total': score_total, 'grade': get_grade(score_total)})
            else:
                student_row['scores'].append({'total': '-', 'grade': '-'})
        student_row['total'] = student_total
        student_row['average'] = round(student_total / len(subjects), 2) if len(subjects) > 0 else 0
        broadsheet_data.append(student_row)
    
    broadsheet_data.sort(key=lambda x: x['total'], reverse=True)
    for i, row in enumerate(broadsheet_data): row['position'] = i + 1

    context = {'student_class': student_class, 'subjects': subjects, 'broadsheet_data': broadsheet_data, 'term': TERM, 'session': SESSION, 'all_terms': ALL_TERMS}
    return render(request, 'results/admin_broadsheet.html', context)