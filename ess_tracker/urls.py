from django.urls import path

from . import views

app_name = 'ess_tracker'

urlpatterns = [
    path('login/', views.ess_login, name='ess_login'),
    path('register/', views.ess_register, name='ess_register'),
    path('logout/', views.ess_logout, name='ess_logout'),
    path('', views.ess_home, name='ess_home'),
    path('profile/', views.ess_profile, name='ess_profile'),
    path('task/new/', views.ess_task_new, name='ess_task_new'),
    path('task/<int:task_id>/edit/', views.ess_task_edit, name='ess_task_edit'),
    path('task/<int:task_id>/autogen/', views.ess_autogen, name='ess_autogen'),
    path('task/<int:task_id>/delete/', views.ess_task_delete, name='ess_task_delete'),
    path('week/', views.ess_week, name='ess_week'),
    path('csv/', views.ess_csv, name='ess_csv'),
    path('fill/', views.ess_fill, name='ess_fill'),
    path('fill/sync/', views.ess_sync_names, name='ess_sync_names'),
    path('fill/push/', views.ess_push_names, name='ess_push_names'),
    path('fill/<int:run_id>/', views.ess_fill_status, name='ess_fill_status'),
    path('fill/<int:run_id>/json/', views.ess_fill_status_json, name='ess_fill_status_json'),
    path('fill/log/', views.ess_fill_log, name='ess_fill_log'),
    path('manifest.webmanifest', views.ess_manifest, name='ess_manifest'),
    path('sw.js', views.ess_sw, name='ess_sw'),
]