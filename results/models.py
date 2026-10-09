from django.db import models
import uuid
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.utils.text import slugify
from django.utils import timezone
from datetime import time
from ckeditor_uploader.fields import RichTextUploadingField
from django.conf import settings

TERM_CHOICES = [
    ('First Term', 'First Term'),
    ('Second Term', 'Second Term'),
    ('Third Term', 'Third Term'),
]
TERM_ORDER = {'First Term': 1, 'Second Term': 2, 'Third Term': 3}
ALL_TERMS = ['First Term', 'Second Term', 'Third Term']

JOINED_TERM_CHOICES = TERM_CHOICES
SESSION = "2025/2026"
LATE_TIME = time(7, 46)

# ========== 1. SCHOOL ==========
class School(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=150, unique=True, blank=True, null=True)
    subdomain = models.CharField(max_length=100, unique=True)
    logo = models.ImageField(upload_to='school_logos/', null=True, blank=True)
    hero_image = models.ImageField(upload_to='school_hero/', null=True, blank=True)
    address = models.TextField()
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    map_embed = models.TextField(blank=True, null=True)
    motto = models.CharField(max_length=300, null=True, blank=True, default='Inspiring Excellence in Education')
    primary_color = models.CharField(max_length=7, default="#004080")
    secondary_color = models.CharField(max_length=7, default="#FFD700")
    current_session = models.CharField(max_length=20, default="2025/2026")
    current_term = models.CharField(max_length=20, choices=TERM_CHOICES, default="Third Term")
    locked_terms = models.CharField(max_length=200, default="", blank=True)
    principal_signature = models.ImageField(upload_to='signatures/', null=True, blank=True)
    principal_name = models.CharField(max_length=200, null=True, blank=True, default="PRINCIPAL") 
    next_term_resumption_date = models.DateField(null=True, blank=True)
    allowed_ips = models.TextField(blank=True, null=True, help_text="Comma separated IPs. e.g: 102.89.45.128, 102.89.45.129")

    # === ADMISSION SAAS FEE - NEW 4 FIELDS ===
    admission_form_fee = models.DecimalField(max_digits=10, decimal_places=2, default=5000, help_text="Form fee e.g 5000 = ₦5,000")
    paystack_public_key = models.CharField(max_length=255, blank=True, help_text="pk_test_xxx or pk_live_xxx")
    paystack_secret_key = models.CharField(max_length=255, blank=True, help_text="sk_test_xxx or sk_live_xxx - KEEP SECRET")
    admission_bank_account = models.CharField(max_length=100, blank=True, help_text="Fallback: e.g 0123456789 - GTB - ECWA Schools")

    def __str__(self):
        return self.name

    def is_term_locked(self, term):
        if not self.locked_terms:
            return False
        locked = [t.strip() for t in self.locked_terms.split(',') if t.strip()]
        return term in locked

    # NEW: Dynamic comment based on student's average
    def get_principal_comment(self, average):
        try:
            avg = float(average)
        except:
            avg = 0
        
        if avg >= 80:
            return "An outstanding performance! You have made us proud. Keep up the excellent work."
        elif avg >= 70:
            return "A very good performance. Keep it up, you can do even better next term."
        elif avg >= 60:
            return "A good result. There is room for improvement. Work harder next term."
        elif avg >= 50:
            return "Fair performance. You need to put in more effort to improve."
        elif avg >= 40:
            return "Below average performance. Please sit up and work harder next term."
        else:
            return "Poor performance. Needs serious improvement and extra attention. See the principal."

# ========== 2. CLASS & ARM ==========
class StudentClass(models.Model):
    SECTION_CHOICES = [
        ('NURSERY', 'Nursery'),
        ('PRIMARY', 'Primary'),
        ('JSS', 'Junior Secondary'),
        ('SSS', 'Senior Secondary'),
    ]
    
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='classes')
    section = models.CharField(max_length=20, choices=SECTION_CHOICES, default='PRIMARY')
    name = models.CharField(max_length=100) # JSS1, SS3, Basic 1
    arm = models.CharField(max_length=10, blank=True, null=True) # A, B, Gold
    class_teacher = models.ForeignKey('Teacher', on_delete=models.SET_NULL, null=True, blank=True, related_name='class_teacher_of')

    class Meta:
        unique_together = ['school', 'name', 'arm']
        ordering = ['section', 'name', 'arm']

    def __str__(self):
        section_name = self.get_section_display()
        return f"{section_name} - {self.name} {self.arm}" if self.arm else f"{section_name} - {self.name}"

# ========== 3. SUBJECT ==========
class Subject(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=50)
    code = models.CharField(max_length=10, blank=True, null=True)

    class Meta:
        unique_together = ['school', 'name']
        ordering = ['name']

    def __str__(self):
        return self.name  # <-- Changed this line

# ========== 4. TEACHER ==========
class Teacher(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='teachers')
    full_name = models.CharField(max_length=200, blank=True, null=True, help_text="If blank, it will use User full name")
    subjects = models.ManyToManyField('Subject', related_name="teachers", blank=True)
    classes = models.ManyToManyField(StudentClass, related_name="teachers", blank=True)
    phone = models.CharField(max_length=15, blank=True, null=True)
    signature = models.ImageField(upload_to='teacher_signatures/', null=True, blank=True)
    passport = models.ImageField(upload_to='teachers/passports/', null=True, blank=True, help_text="Passport for ID Card") # <-- NEW

    def __str__(self):
        name = self.full_name or self.user.get_full_name() or self.user.username
        return name

# ========== 5. ASSESSMENT COMPONENT ==========
class AssessmentComponent(models.Model):
    SECTION_CHOICES = [
        ('NURSERY', 'Nursery'),
        ('PRIMARY', 'Primary'),
        ('JSS', 'Junior Secondary'),
        ('SSS', 'Senior Secondary'),
    ]
    
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='components')
    section = models.CharField(max_length=20, choices=SECTION_CHOICES, default='PRIMARY')
    name = models.CharField(max_length=50) # CA1, CA2, EXAM, Handwriting
    max_score = models.IntegerField()
    min_score = models.FloatField(default=0)
    order = models.IntegerField(default=1)

    class Meta:
        ordering = ['section', 'order']
        unique_together = ['school', 'section', 'name']

    def __str__(self):
        return f"{self.name} [{self.max_score}] - {self.section}"

# ========== 6. GRADE SCALE ==========
class GradeScale(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='grades')
    grade = models.CharField(max_length=5) # A1, B2, C4
    min_score = models.IntegerField()
    max_score = models.IntegerField()
    remark = models.CharField(max_length=50)

    class Meta:
        unique_together = ['school', 'grade']
        ordering = ['-min_score']

    def __str__(self):
        return f"{self.grade} [{self.min_score}-{self.max_score}]"

# ========== 7. SCRATCH CARD ==========
class ScratchCard(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    pin = models.CharField(max_length=20, unique=True)
    amount = models.IntegerField(default=1000)
    usage_count = models.IntegerField(default=0)  # NEW
    max_usage = models.IntegerField(default=3)  # NEW - 3 times
    used = models.BooleanField(default=False)
    used_by_student = models.ForeignKey('Student', on_delete=models.SET_NULL, null=True, blank=True)
    date_used = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_fully_used(self):
        return self.usage_count >= self.max_usage

    def can_use(self):
        return self.usage_count < self.max_usage

    def __str__(self):
        return f"{self.pin} - {self.school.name} ({self.usage_count}/{self.max_usage})"
# ========== 8. STUDENT ==========
class Student(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student_class = models.ForeignKey(StudentClass, on_delete=models.CASCADE, related_name='students')
    admission_no = models.CharField(max_length=50)
    full_name = models.CharField(max_length=200)
    joined_term = models.CharField(max_length=20, choices=JOINED_TERM_CHOICES, default="First Term")
    password = models.CharField(max_length=128, blank=True, default='')
    pin = models.CharField(max_length=6, default='1234')
    gender = models.CharField(max_length=10, choices=[('Male','Male'),('Female','Female')], blank=True, null=True)
    parent_name = models.CharField(max_length=100, blank=True, null=True)
    parent_phone = models.CharField(max_length=15, blank=True, null=True)
    parent_email = models.EmailField(max_length=255, blank=True, null=True)
    passport = models.ImageField(upload_to='student_passports/', null=True, blank=True)
    transcript_pin = models.CharField(max_length=10, null=True, blank=True)

    class Meta:
        unique_together = ['school', 'admission_no']
        ordering = ['full_name']

    def __str__(self):
        return f"{self.admission_no} - {self.full_name}"

    def save(self, *args, **kwargs):
        if not self.password:
            self.password = make_password(self.admission_no)
        elif not self.password.startswith('pbkdf2'):
            self.password = make_password(self.password)
        super().save(*args, **kwargs)

    def get_divisor(self, current_term):
        current_order = TERM_ORDER.get(current_term, 1)
        joined_order = TERM_ORDER.get(self.joined_term, 1)
        divisor = current_order - joined_order + 1
        return max(1, divisor)

# ========== 9. STUDENT SUBJECT ==========
class StudentSubject(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='offered_subjects')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    student_class = models.ForeignKey(StudentClass, on_delete=models.CASCADE)

    class Meta:
        unique_together = ['student', 'subject']
        ordering = ['student']

    def __str__(self):
        return f"{self.student} - {self.subject.name}"

# ========== 10. SCORE MODEL ==========
class StudentScore(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='scores')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    term = models.CharField(max_length=20, choices=TERM_CHOICES, default="First Term")
    session = models.CharField(max_length=20, default="2025/2026")
    component = models.ForeignKey(AssessmentComponent, on_delete=models.CASCADE)
    score = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        unique_together = ['student', 'subject', 'term', 'session', 'component']
        ordering = ['subject', 'component']

    def clean(self):
        if self.score and self.score > self.component.max_score:
            raise ValidationError(f'Score cannot be more than {self.component.max_score}')
        if self.score and self.score < 0:
            raise ValidationError('Score cannot be negative')

    def __str__(self):
        return f"{self.student} - {self.subject} - {self.component.name}: {self.score}"

# ========== 11. STUDENT NOTE ==========
class StudentNote(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='notes')
    student_class = models.ForeignKey(StudentClass, on_delete=models.CASCADE, related_name='notes')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE)
    term = models.CharField(max_length=20, choices=TERM_CHOICES)
    session = models.CharField(max_length=20)
    title = models.CharField(max_length=200)
    note = RichTextUploadingField()
    file = models.FileField(upload_to='notes/', blank=True, null=True)
    is_approved = models.BooleanField(default=False)
    is_read = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self): return f"{self.title} - {self.student_class}"

# ========== 12. CA TEST ==========
class CATest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='catests')
    student_class = models.ForeignKey(StudentClass, on_delete=models.CASCADE, related_name='catests')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE)
    term = models.CharField(max_length=20, choices=TERM_CHOICES)
    session = models.CharField(max_length=20)
    title = models.CharField(max_length=200)
    instructions = models.TextField(blank=True, null=True)
    test_date = models.DateField()
    max_score = models.IntegerField(default=20)
    access_token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    duration_minutes = models.PositiveIntegerField(default=30, help_text="How many minutes for this test")
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "CA Test"
        verbose_name_plural = "CA Tests"
        ordering = ['-created_at']

    def get_access_url(self, request):
        return request.build_absolute_uri(f'/take-ca/{self.access_token}/')

    def __str__(self): 
        return f"{self.title} - {self.subject.name} - {self.status}"

class CATestQuestion(models.Model):
    QUESTION_TYPES = (
        ('text', 'Theory/Essay'),
        ('mcq', 'Multiple Choice'),
    )
    test = models.ForeignKey(CATest, on_delete=models.CASCADE, related_name='questions')
    question_number = models.IntegerField()
    question_type = models.CharField(max_length=10, choices=QUESTION_TYPES, default='mcq')
    question_text = models.TextField(blank=True, null=True)
    question_image = models.ImageField(upload_to='ca_test_questions/', blank=True, null=True)
    option_a = models.CharField(max_length=500, blank=True, null=True)
    option_b = models.CharField(max_length=500, blank=True, null=True)
    option_c = models.CharField(max_length=500, blank=True, null=True)
    option_d = models.CharField(max_length=500, blank=True, null=True)
    correct_answer = models.CharField(max_length=1, choices=[('A','A'),('B','B'),('C','C'),('D','D')], blank=True, null=True)
    marks = models.IntegerField(default=1)

    class Meta:
        verbose_name = "CA Test Question"
        verbose_name_plural = "CA Test Questions"
        ordering = ['question_number']

    def __str__(self):
        return f"Q{self.question_number} - {self.test.title}"

class CATestResult(models.Model):
    test = models.ForeignKey(CATest, on_delete=models.CASCADE, related_name='results')
    student_name = models.CharField(max_length=200)
    student_adm_no = models.CharField(max_length=50, blank=True, null=True)
    score = models.IntegerField()
    percentage = models.FloatField()
    submitted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "CA Test Result"
        verbose_name_plural = "CA Test Results"
        ordering = ['-submitted_at']

    def __str__(self):
        return f"{self.student_name} - {self.test.title} - {self.score}"
    
# ========== 12b. CA SESSION & ANSWERS ==========
class StudentCASession(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    ca_test = models.ForeignKey(CATest, on_delete=models.CASCADE)
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    is_submitted = models.BooleanField(default=False)
    score = models.IntegerField(default=0)

    class Meta:
        unique_together = ['student', 'ca_test'] # 1 attempt per CA
        verbose_name = "CA Test Session"
        verbose_name_plural = "CA Test Sessions"

    def __str__(self):
        return f"{self.student} - {self.ca_test.title}"

class StudentCAAnswer(models.Model):
    session = models.ForeignKey(StudentCASession, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(CATestQuestion, on_delete=models.CASCADE)
    selected_answer = models.CharField(max_length=1, null=True, blank=True)
    
    class Meta:
        unique_together = ['session', 'question']
        verbose_name = "CA Test Answer"
        verbose_name_plural = "CA Test Answers"

    def __str__(self):
        return f"{self.session} - Q{self.question_number}"

# ========== 13. STUDENT ATTENDANCE ==========
class Attendance(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student_class = models.ForeignKey(StudentClass, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE)
    date = models.DateField()
    term = models.CharField(max_length=20, choices=TERM_CHOICES)
    session = models.CharField(max_length=20)
    status = models.CharField(max_length=10, choices=[('Present','Present'),('Absent','Absent'),('Late','Late')])

    class Meta:
        unique_together = ['student', 'date']
        ordering = ['-date']

    def __str__(self): return f"{self.student} - {self.date} - {self.status}"

# ========== 14. CBT TEST ==========
class Test(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    test_class = models.ForeignKey(StudentClass, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    duration_minutes = models.IntegerField(default=30)
    created_by = models.ForeignKey(Teacher, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} - {self.subject.name}"

class Question(models.Model):
    test = models.ForeignKey(Test, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    question_image = models.ImageField(upload_to='cbt_questions/', blank=True, null=True)
    option_a = models.CharField(max_length=255)
    option_b = models.CharField(max_length=255)
    option_c = models.CharField(max_length=255)
    option_d = models.CharField(max_length=255)
    correct_answer = models.CharField(max_length=1, choices=[('A','A'),('B','B'),('C','C'),('D','D')])
    marks = models.PositiveIntegerField(default=1)

    def __str__(self):
        return self.question_text[:50]

class StudentTestSession(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    test = models.ForeignKey(Test, on_delete=models.CASCADE)
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    is_submitted = models.BooleanField(default=False)
    score = models.IntegerField(default=0)

class StudentAnswer(models.Model):
    session = models.ForeignKey(StudentTestSession, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_answer = models.CharField(max_length=1, null=True, blank=True)

# ========== 15. STAFF ==========
class Staff(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='staff')
    full_name = models.CharField(max_length=200)
    staff_id = models.CharField(max_length=50)
    device_staff_id = models.CharField(max_length=50, blank=True, null=True)
    phone = models.CharField(max_length=15, blank=True, null=True)
    designation = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        unique_together = ['school', 'staff_id']

    def __str__(self):
        return f"{self.full_name} - {self.staff_id}"

# ========== 16. STAFF ATTENDANCE ==========
class StaffAttendance(models.Model):
    STATUS_CHOICES = [('Present', 'Present'), ('Late', 'Late'), ('Absent', 'Absent'), ('Half-Day', 'Half-Day')]

    school = models.ForeignKey(School, on_delete=models.CASCADE)
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name='attendances')
    date = models.DateField()
    term = models.CharField(max_length=20, choices=TERM_CHOICES)
    session = models.CharField(max_length=20, default=SESSION)
    time_in = models.TimeField(null=True, blank=True)
    time_out = models.TimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Present')

    class Meta:
        unique_together = ('staff', 'date')
        ordering = ['-date']

    def save(self, *args, **kwargs):
        if self.time_in:
            self.status = 'Late' if self.time_in > LATE_TIME else 'Present'
        if self.time_out and self.time_out < time(13, 0):
            self.status = 'Half-Day'
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.staff.full_name} - {self.date} - {self.status}"

# ========== 17. GALLERY ==========
class Gallery(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='gallery')
    title = models.CharField(max_length=200)
    image = models.ImageField(upload_to='gallery/')
    category = models.CharField(max_length=50, default='General')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.school.name} - {self.title}"

# ========== 18. TEACHER'S COMMENT ==========
class TeacherNote(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='teacher_notes')
    term = models.CharField(max_length=20, choices=TERM_CHOICES)
    session = models.CharField(max_length=20)
    note = models.TextField()
    teacher = models.ForeignKey(Teacher, on_delete=models.SET_NULL, null=True, blank=True)
    is_approved = models.BooleanField(default=False)
    date = models.DateField(auto_now_add=True)

    class Meta:
        unique_together = ['student', 'term', 'session']

    def __str__(self):
        return f"{self.student.full_name} - {self.term} {self.session}"

#======= 19. NEWS MODEL =======
class News(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='news')
    title = models.CharField(max_length=200)
    content = models.TextField()
    date_posted = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-date_posted']
        verbose_name_plural = "News & Announcements"

    def __str__(self):
        return f"{self.school.name} - {self.title}"

    #===== WHY CHOOSE US CARD ===========
class WhyChooseUsCard(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='why_cards')
    ICON_CHOICES = [
        ('mortarboard', 'Quality Education - mortarboard'),
        ('laptop', 'Modern Facilities - laptop'),
        ('shield-check', 'Safe Environment - shield-check'),
        ('trophy', 'Extra-Curricular - trophy'),
        ('book', 'Library - book'),
        ('people', 'Users - people'),
        ('building', 'Lab/Infrastructure - building'),
        ('heart-pulse', 'Heart/Health - heart-pulse'),
    ]
    icon = models.CharField(max_length=50, choices=ICON_CHOICES, default='mortarboard')
    title = models.CharField(max_length=100, help_text="e.g. Quality Education")
    description = models.TextField(max_length=300, help_text="e.g. Experienced teachers...")
    order = models.PositiveIntegerField(default=0, help_text="1,2,3,4 - controls display order")

    class Meta:
        ordering = ['order']
        verbose_name = "Why Choose Us Card"
        verbose_name_plural = "Why Choose Us Cards"

    def __str__(self):
        return f"{self.school.name} - {self.title}"

# ========== 20. ONLINE ADMISSION ==========
class AdmissionApplication(models.Model):
    GENDER_CHOICES = [
        ('Male','Male'),
        ('Female','Female'),
    ]
    STATUS_CHOICES = [
        ('Pending','Pending'),
        ('Paid','Paid'),
        ('Reviewed','Reviewed'),
        ('Admitted','Admitted'),
        ('Rejected','Rejected'),
    ]

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='admissions')
    full_name = models.CharField(max_length=200)
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES)
    class_applying = models.CharField(max_length=50, help_text="e.g JSS1, SS1, Primary 1")
    previous_school = models.CharField(max_length=200, blank=True, null=True)
    
    parent_name = models.CharField(max_length=200)
    parent_phone = models.CharField(max_length=20)
    parent_email = models.EmailField(blank=True, null=True)
    parent_address = models.TextField()
    relationship = models.CharField(max_length=50, default="Father")

    passport = models.ImageField(upload_to='admissions/passports/', blank=True, null=True)
    
    # === SAAS PAYMENT FIELDS - NEW ===
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_paid = models.BooleanField(default=False)
    paystack_ref = models.CharField(max_length=120, blank=True, null=True)
    payment_date = models.DateTimeField(null=True, blank=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    applied_on = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.full_name} - {self.class_applying} ({self.status}) - {'PAID' if self.is_paid else 'UNPAID'}"

    class Meta:
        ordering = ['-applied_on']

#======== LESSON PLAN ========
class LessonPlan(models.Model):
    school = models.ForeignKey('School', on_delete=models.CASCADE)
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    student_class = models.CharField(max_length=100)  # store class name/id as text for now
    subject = models.CharField(max_length=100)
    week = models.CharField(max_length=20)
    topic = models.CharField(max_length=255)
    objectives = models.TextField()
    activities = models.TextField()
    materials = models.CharField(max_length=500, blank=True)
    assignment = models.TextField(blank=True)
    is_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.topic} - {self.week}"

#===== PSHYCHOMOTOR =========
class Psychomotor(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    term = models.CharField(max_length=20, default='1st Term')
    session = models.CharField(max_length=20, default='2025/2026')
    punctuality = models.IntegerField(default=0)
    neatness = models.IntegerField(default=0)
    honesty = models.IntegerField(default=0)
    politeness = models.IntegerField(default=0)
    attentiveness = models.IntegerField(default=0)
    handwriting = models.IntegerField(default=0)
    games_sports = models.IntegerField(default=0)
    handling_tools = models.IntegerField(default=0)
    drawing = models.IntegerField(default=0)
    leadership = models.IntegerField(default=0)

    class Meta:
        unique_together = ('student', 'term', 'session')