from django.urls import path
from . import views

app_name = 'curriculum'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),

    # Scheme of Work
    path('scheme/', views.generate_scheme_view, name='generate_scheme'),
    path('scheme/ajax-generate/', views.ajax_generate_scheme, name='ajax_generate_scheme'),
    path('scheme/ajax-load-saved/', views.ajax_load_saved_scheme, name='ajax_load_saved_scheme'),
    path('scheme/download-pdf/', views.download_scheme_pdf, name='download_scheme_pdf'),
    path('scheme/download-word/', views.download_scheme_word, name='download_scheme_word'),

    # Lesson Plan
    path('lesson-plan/', views.lesson_plan_view, name='lesson_plan'),
    path('lesson-plan/ajax-generate/', views.ajax_generate_lessonplan, name='ajax_generate_lessonplan'),
    path('lesson-plan/ajax-load-saved/', views.ajax_load_saved_lessonplan, name='ajax_load_saved_lessonplan'),
    path('lesson-plan/download-pdf/', views.download_lesson_plan_pdf, name='download_lesson_plan_pdf'),
    path('lesson-plan/download-word/', views.download_lesson_plan_word, name='download_lesson_plan_word'),

    # Logbook
    path('logbook/', views.submit_logbook, name='submit_logbook'),
    path('logbook/history/', views.logbook_history, name='logbook_history'),
    path('logbook/download/<str:period_type>/', views.download_logbook_pdf, name='download_logbook_pdf'),
    path('logbook/download-options/', views.logbook_download_options, name='logbook_download_options'),

    # API helpers
    path('api/get-classes/', views.get_classes_by_level, name='get_classes'),
    path('api/get-subjects-by-level/', views.get_subjects_by_level, name='get_subjects_by_level'),
    path('api/get-textbooks/', views.get_textbooks_by_level, name='get_textbooks'),
]
