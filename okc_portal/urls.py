from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from results import views
from results.ckeditor_upload import upload
from ckeditor_uploader.views import browse
from django.shortcuts import redirect

urlpatterns = [
    path('', views.home_redirect, name='root_home'),
    path('admin/', admin.site.urls), 
    
    path('ckeditor/upload/', upload, name='ckeditor_upload'),
    path('ckeditor/browse/', browse, name='ckeditor_browse'),
    
    path('student-login/', views.student_login_global, name='student_login'),
    path('admin-login/', views.custom_logout, name='admin_login_redirect'),
    path('admin-logout/', views.custom_logout, name='admin_logout'),
    path('home/', views.home_redirect, name='home_redirect'),
    
    path('<slug:school_slug>/bulk-allocate-subjects/', views.bulk_allocate_subjects, name='bulk_allocate_subjects'),
    path('<slug:school_slug>/transcript/<int:student_id>/', views.student_transcript, name='student_transcript'),
    
    # ID CARDS - STUDENTS
    path('<slug:school_slug>/id-cards/', views.print_id_cards, name='print_id_cards'),
    path('<slug:school_slug>/verify/<str:admission_no>/', views.verify_student_id, name='verify_student_id'),
    
    # ID CARDS - TEACHERS - NEW
    path('<slug:school_slug>/teacher-id-cards/', views.print_teacher_id_cards, name='print_teacher_id_cards'),
    path('<slug:school_slug>/teacher-verify/<str:staff_id>/', views.verify_teacher_id, name='verify_teacher_id'),
    
    path('<slug:school_slug>/admin-login/', views.school_admin_login, name='school_admin_login'),
    path('<slug:school_slug>/admin/', views.school_admin_redirect, name='school_admin_redirect'),
    path('<slug:school_slug>/student-login/', views.student_login, name='school_student_login'),
    path('<slug:school_slug>/student-logout/', views.student_logout, name='school_student_logout'),
    
    # NEWS DETAIL - MUST BE BEFORE school_landing !!!
    path('<slug:school_slug>/news/<int:news_id>/', views.news_detail, name='news_detail'),
    
    # SCHOOL LANDING PAGE - KEEP THIS SECOND TO LAST
    path('<slug:school_slug>/', views.school_landing, name='school_landing_main'),
    
    # CATCH-ALL FOR SCHOOL PORTAL MUST BE LAST
    path('<slug:school_slug>/portal/', include('results.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)