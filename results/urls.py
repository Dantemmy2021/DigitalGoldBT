from django.urls import path
from . import views

app_name = 'results'

urlpatterns = [
    path('', views.home_redirect, name='home_redirect'),
    path('teacher/', views.teacher_dashboard, name='teacher_dashboard'),
    path('teacher/enter-scores/<int:subject_id>/', views.enter_scores, name='enter_scores'),
    path('teacher/print/<int:student_id>/', views.print_result, name='print_result'),
    
    # ADMIN PRINTS
    path('teacher/admin/print-student/<int:student_id>/', views.admin_print_student, name='admin_print_student'),
    path('teacher/admin/broadsheet/<int:class_id>/', views.admin_broadsheet, name='admin_broadsheet'), # NEW
]