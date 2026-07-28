from django.urls import path
from . import views

app_name = 'curriculum'

urlpatterns = [
    # Landing page (public, School Results login style)
    path('', views.landing, name='landing'),

    # Dashboard (login required)
    path('dashboard/', views.dashboard, name='dashboard'),

    # Scheme of Work
    path('scheme/', views.generate_scheme_view, name='generate_scheme'),
    path('scheme/ajax-generate/', views.ajax_generate_scheme, name='ajax_generate_scheme'),
    path('scheme/ajax-load-saved/', views.ajax_load_saved_scheme, name='ajax_load_saved_scheme'),
    path('scheme/ajax-load-by-id/<int:scheme_id>/', views.ajax_load_scheme_by_id, name='ajax_load_scheme_by_id'),
    path('scheme/download-pdf/', views.download_scheme_pdf, name='download_scheme_pdf'),
    path('scheme/download-word/', views.download_scheme_word, name='download_scheme_word'),

    # Lesson Plan
    path('lesson-plan/', views.lesson_plan_view, name='lesson_plan'),
    path('lesson-plan/ajax-generate/', views.ajax_generate_lessonplan, name='ajax_generate_lessonplan'),
    path('lesson-plan/ajax-load-saved/', views.ajax_load_saved_lessonplan, name='ajax_load_saved_lessonplan'),
    path('lesson-plan/ajax-load-by-id/<int:lesson_id>/', views.ajax_load_lesson_by_id, name='ajax_load_lesson_by_id'),
    path('lesson-plan/download-pdf/', views.download_lesson_plan_pdf, name='download_lesson_plan_pdf'),
    path('lesson-plan/download-word/', views.download_lesson_plan_word, name='download_lesson_plan_word'),

    # Lesson Notes
    path('lesson-notes/', views.lesson_notes_view, name='lesson_notes'),
    path('lesson-notes/ajax-save/', views.ajax_save_lesson_note, name='save_lesson_note'),
    path('lesson-notes/ajax-get/<int:note_id>/', views.ajax_get_lesson_note, name='get_lesson_note'),
    path('lesson-notes/ajax-delete/', views.ajax_delete_lesson_note, name='delete_lesson_note'),

    # Logbook
    path('logbook/', views.submit_logbook, name='submit_logbook'),
    path('logbook/history/', views.logbook_history, name='logbook_history'),
    path('logbook/download/<str:period_type>/', views.download_logbook_pdf, name='download_logbook_pdf'),
    path('logbook/download-options/', views.logbook_download_options, name='logbook_download_options'),

    # Teacher Registration (no login)
    path('register/', views.teacher_register, name='teacher_register'),
    path('logout/', views.tlm_logout, name='tlm_logout'),
    path('api/get-districts/', views.ajax_get_districts, name='get_districts'),
    path('api/get-schools/', views.ajax_get_schools, name='get_schools'),
    path('api/save-teacher/', views.ajax_save_teacher, name='save_teacher'),
    path('api/lookup-teacher/', views.ajax_lookup_teacher, name='lookup_teacher'),

    # Save edited content
    path('scheme/ajax-save-edits/', views.ajax_save_scheme_edits, name='save_scheme_edits'),
    path('lesson-plan/ajax-save-edits/', views.ajax_save_lesson_edits, name='save_lesson_edits'),

    # Template Library
    path('library/', views.template_library, name='template_library'),

    # Testimonials
    path('api/submit-testimonial/', views.ajax_submit_testimonial, name='submit_testimonial'),

    # Profile auto-save (for old users)
    path('api/update-teacher-profile/', views.ajax_update_teacher_profile, name='update_teacher_profile'),

    # API helpers
    path('api/get-topics/', views.ajax_get_topics_db, name='get_topics_db'),
    path('api/get-subtopics/', views.ajax_get_subtopics_db, name='get_subtopics_db'),
    path('api/get-topics-ai/', views.get_topics_ai, name='get_topics_ai'),
    path('api/get-subtopics-ai/', views.get_subtopics_ai, name='get_subtopics_ai'),
    path('api/get-classes/', views.get_classes_by_level, name='get_classes'),
    path('api/get-subjects-by-level/', views.get_subjects_by_level, name='get_subjects_by_level'),
    path('api/get-textbooks/', views.get_textbooks_by_level, name='get_textbooks'),
    path('api/search-schools/', views.ajax_search_schools, name='search_schools'),
    path('api/submit-update-comment/', views.ajax_submit_update_comment, name='submit_update_comment'),
]
