from django.urls import path
from . import views

app_name = 'results'

urlpatterns = [
    # PORTAL LANDING - /ecwa-schools/portal/
    path('', views.portal_login, name='portal_login'),
    
    # SCHOOL ADMIN
    path('admin-login/', views.school_admin_login, name='school_admin_login'),
    path('admin/', views.school_admin_redirect, name='school_admin_redirect'),
    
    path('parent-transcript/', views.parent_transcript_login, name='parent_transcript_login'),
    path('student/dashboard/', views.student_dashboard, name='student_dashboard'),

    # STUDENT
    path('student/', views.student_login, name='student_login'),
    path('student/tests/', views.student_tests, name='student_tests'),
    path('student/take-test/<int:session_id>/', views.take_test, name='take_test'),
    path('student/result/<int:session_id>/', views.test_result, name='test_result'),
    path('student/notes/', views.student_notes, name='student_notes'),
    path('student/notes/<int:note_id>/', views.student_note_detail, name='student_note_detail'),
    path('student/logout/', views.student_logout, name='student_logout'),

    # AUTH
    path('parent/login/', views.parent_login, name='parent_login'),
    path('teacher/login/', views.school_teacher_login, name='school_teacher_login'),
    path('logout/', views.custom_logout_school, name='logout'),

    # TEACHER
    path('dashboard/', views.teacher_dashboard, name='teacher_dashboard'),
    path('enter/<int:subject_id>/', views.enter_scores, name='enter_scores'),
    path('print/<int:student_id>/', views.print_result, name='print_result'),
    path('note/', views.teacher_give_note, name='teacher_give_note'),
    path('ca-test/', views.teacher_ca_test, name='teacher_ca_test'),
    path('attendance/', views.teacher_take_attendance, name='teacher_take_attendance'),
    path('teacher/lesson-plan/', views.teacher_lesson_plan, name='teacher_lesson_plan'),

    # ADMIN TOOLS
    path('broadsheet/<int:class_id>/', views.admin_broadsheet, name='admin_broadsheet'),
    path('broadsheet/pdf/<int:class_id>/', views.download_broadsheet_pdf, name='download_broadsheet_pdf'),
    path('admin/print/<int:student_id>/', views.admin_print_student, name='admin_print_student'),
    path('admin/reset-test/<int:session_id>/', views.reset_test, name='reset_test'),

    # PARENT / STUDENT
    path('parent/print/<int:student_id>/', views.parent_print_result, name='parent_print_result'),
    path('transcript/<int:student_id>/', views.view_transcript, name='view_transcript'),
    path('parent/download/<int:student_id>/', views.parent_download_result, name='parent_download_result'),
    
    # CA TEST
    path('take-ca/<int:ca_id>/', views.take_ca, name='take_ca'),
    path('bulk-allocate-subjects/', views.bulk_allocate_subjects, name='bulk_allocate_subjects'),

    # NEWS
    path('news/<int:news_id>/', views.news_detail, name='news_detail'),

    # ADMISSION
    path('admission/apply/', views.admission_apply, name='admission_apply'),
    path('admission/success/<int:pk>/', views.admission_success, name='admission_success'),
    path('admission/verify/<int:pk>/', views.admission_verify_payment, name='admission_verify_payment'),

    path('teacher/psychomotor/', views.psychomotor_class_list, name='psychomotor_class_list'),
    path('teacher/psychomotor/class/<int:class_id>/', views.psychomotor_student_list, name='psychomotor_student_list'),
    path('teacher/psychomotor/rate/<int:student_id>/', views.rate_psychomotor, name='rate_psychomotor'),

    # ID CARDS - ONLY ONCE EACH
    path('id-cards/', views.print_id_cards, name='print_id_cards'),
    path('id-cards/verify/<str:admission_no>/', views.verify_student_id, name='verify_student_id'),
    path('teacher-id-cards/', views.print_teacher_id_cards, name='print_teacher_id_cards'),
    path('teacher-id-cards/verify/<str:staff_id>/', views.verify_teacher_id, name='verify_teacher_id'),
]