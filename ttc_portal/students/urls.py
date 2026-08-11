from django.urls import path
from students import views

urlpatterns = [
    path('register/', views.register, name='register'),
    path('dashboard/', views.dashboard, name='dashboard'),
    # College admin
    path('college-admin/', views.admin_dashboard, name='admin_dashboard'),
    path('college-admin/wanafunzi/', views.admin_students, name='admin_students'),
    path('college-admin/wanafunzi/ongeza/', views.admin_add_student, name='admin_add_student'),
    path('college-admin/wanafunzi/<int:student_id>/', views.admin_student_detail, name='admin_student_detail'),
    # Super admin
    path('super-admin/', views.super_admin_dashboard, name='super_admin_dashboard'),
]
