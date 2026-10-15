from django.urls import path

from . import views

app_name = 'ess_tracker'

urlpatterns = [
    path('login/', views.ess_login, name='ess_login'),
    path('register/', views.ess_register, name='ess_register'),
    path('recover/', views.ess_recover, name='ess_recover'),
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
    path('approve/', views.ess_approve_page, name='ess_approve'),
    path('approve/run/', views.ess_approve_now, name='ess_approve_now'),
    path('fill/sync/', views.ess_sync_names, name='ess_sync_names'),
    path('fill/push/', views.ess_push_names, name='ess_push_names'),
    path('fill/read/', views.ess_read_pcts, name='ess_read_pcts'),
    path('fill/auto-choice/', views.ess_save_auto_choice, name='ess_save_auto_choice'),
    path('fill/<int:run_id>/', views.ess_fill_status, name='ess_fill_status'),
    path('fill/<int:run_id>/json/', views.ess_fill_status_json, name='ess_fill_status_json'),
    path('fill/log/', views.ess_fill_log, name='ess_fill_log'),
    path('manifest.webmanifest', views.ess_manifest, name='ess_manifest'),
    path('sw.js', views.ess_sw, name='ess_sw'),
    path('push/key/', views.ess_push_key, name='ess_push_key'),
    path('push/subscribe/', views.ess_push_subscribe, name='ess_push_subscribe'),
    path('push/unsubscribe/', views.ess_push_unsubscribe, name='ess_push_unsubscribe'),
    path('push/test/', views.ess_push_test, name='ess_push_test'),
]