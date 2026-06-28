from django.urls import path
from . import views

app_name = 'transfer'

urlpatterns = [
    path('', views.home, name='home'),
    path('register/', views.register, name='register'),
    path('browse/', views.browse_regions, name='browse_regions'),
    path('browse/<int:region_id>/', views.browse_districts, name='browse_districts'),
    path('browse/<int:region_id>/<int:district_id>/', views.teachers_in_district, name='teachers_in_district'),
    path('unlock/<int:teacher_id>/', views.unlock_contact, name='unlock_contact'),
    path('buy/', views.buy_credits, name='buy_credits'),
    path('pay/', views.submit_payment, name='submit_payment'),
    path('login/', views.login_returning, name='login'),
    path('ajax/districts/', views.get_districts_ajax, name='get_districts_ajax'),
    path('deactivate/', views.deactivate, name='deactivate'),
]
