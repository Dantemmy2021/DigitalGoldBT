from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

TERM_CHOICES = [
    ('First Term', 'First Term'),
    ('Second Term', 'Second Term'),
    ('Third Term', 'Third Term'),
]

JOINED_TERM_CHOICES = [
    ('First Term', 'First Term'),
    ('Second Term', 'Second Term'),
    ('Third Term', 'Third Term'),
]

class Student(models.Model):
    admission_no = models.CharField(max_length=20, unique=True)
    full_name = models.CharField(max_length=100)
    student_class = models.CharField(max_length=10)
    arm = models.CharField(max_length=10)
    joined_term = models.CharField(max_length=20, choices=JOINED_TERM_CHOICES, default="First Term") # <-- ADD THIS

    def __str__(self): 
        return self.full_name

    def get_divisor(self, current_term): # <-- PUT IT HERE INSIDE STUDENT CLASS
        """
        Returns how many terms to divide cumulative by
        """
        if self.joined_term == 'Third Term':
            return 1  # Only 3rd term
        elif self.joined_term == 'Second Term':
            if current_term == 'Third Term':
                return 2  # 2nd + 3rd
            else:
                return 1  # Only 2nd
        else: # Joined First Term
            if current_term == 'First Term':
                return 1
            elif current_term == 'Second Term':
                return 2
            else: # Third Term
                return 3

class Subject(models.Model):
    name = models.CharField(max_length=50)
    student_class = models.CharField(max_length=10)
    teachers = models.ManyToManyField(User, blank=True, related_name='subjects_taught')
    
    def __str__(self): 
        return f"{self.name} - {self.student_class}"

class Score(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    term = models.CharField(max_length=20, choices=TERM_CHOICES, default="Second Term")
    session = models.CharField(max_length=20, default="2025/2026")
    ca1 = models.IntegerField(default=0)
    ca2 = models.IntegerField(default=0)
    project = models.IntegerField(default=0)
    assignment = models.IntegerField(default=0)
    exam = models.IntegerField(default=0)
    
    def clean(self):
        total = self.ca1 + self.ca2 + self.project + self.assignment + self.exam
        if total > 100:
            raise ValidationError(f'Total score cannot exceed 100. Current total is {total}')
        if self.ca1 > 10 or self.ca2 > 10 or self.project > 10 or self.assignment > 10:
            raise ValidationError('CA1, CA2, Project, Assignment cannot be more than 10')
        if self.exam > 60:
            raise ValidationError('Exam cannot be more than 60')
    
    def save(self, *args, **kwargs):
        self.full_clean() 
        super().save(*args, **kwargs)
    
    @property
    def total(self): 
        return self.ca1 + self.ca2 + self.project + self.assignment + self.exam
    
    @property
    def grade(self):
        total = self.total
        if total >= 70: return 'A'
        elif total >= 60: return 'B'
        elif total >= 50: return 'C'
        elif total >= 45: return 'D'
        elif total >= 40: return 'E'
        else: return 'F'
        
    def __str__(self): 
        return f"{self.student} - {self.subject}"