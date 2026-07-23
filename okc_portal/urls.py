from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from results import views

urlpatterns = [
    path('', views.home_redirect, name='home'),
    path('admin/', admin.site.urls),
    path('teacher/', include('results.urls')), # everything for results app goes here
    path('accounts/login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('accounts/', include('django.contrib.auth.urls')),
]