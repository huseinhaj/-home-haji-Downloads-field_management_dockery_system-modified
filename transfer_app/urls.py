from django.urls import path
from . import views

app_name = 'transfer'

urlpatterns = [
    path('', views.home, name='home'),
    path('register/', views.register, name='register'),
    path('browse/', views.browse_regions, name='browse_regions'),
    path('browse/<int:region_id>/', views.browse_districts, name='browse_districts'),
    path('browse/<int:region_id>/<int:district_id>/', views.teachers_in_district, name='teachers_in_district'),
    path('donate/', views.donate, name='donate'),
    path('login/', views.login_returning, name='login'),
    path('ajax/districts/', views.get_districts_ajax, name='get_districts_ajax'),
    path('logout/', views.logout_transfer, name='logout'),
    path('deactivate/', views.deactivate, name='deactivate'),
]
