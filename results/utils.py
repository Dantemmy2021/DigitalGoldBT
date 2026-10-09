from .models import Student, GradeScale, StudentScore

def get_student(request, school):
    """Get logged in student from session"""
    student_id = request.session.get('student_id')
    if student_id:
        try:
            return Student.objects.get(id=student_id, school=school)
        except Student.DoesNotExist:
            return None
    return None

def get_grade_and_remark(school, score):
    """Convert score to grade and remark based on school grade scale"""
    score = float(score)
    grade_obj = GradeScale.objects.filter(
        school=school, 
        min_score__lte=score, 
        max_score__gte=score
    ).first()
    
    if grade_obj:
        return grade_obj.grade, grade_obj.remark
    return 'F9', 'Fail'

def get_student_subject_total(student, subject, term, session):
    """Get total score for a subject in a term"""
    scores = StudentScore.objects.filter(
        student=student,
        subject=subject,
        term=term,
        session=session
    )
    return sum(s.score for s in scores)