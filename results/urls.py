from django.urls import path
from .views import (
    home,
    upload_results,
    generate_results_pdf,
    export_results_excel,
    filter_exams,
    exam_overview,
    subject_upload,
    subject_pdf,
    finalize_exam,
    upload_roster,
    academic_dashboard,
    approve_subject,
    approve_exam_submissions,
    form_results,
    form_results_excel,
    school_setup,
    school_subjects,
    create_exam_for_school,
    teacher_dashboard,
)
from .speech_views import (
    confirm_speech_candidate,
    create_speech_session,
    finalize_speech_session,
    ingest_speech_entry,
    speech_entry_page,
    speech_session_status,
)

urlpatterns = [
    path('', home, name='home'),
    path('upload/', upload_results, name='upload_results'),
    path('results-pdf/<int:exam_id>/', generate_results_pdf, name='generate_results_pdf'),
    path('results-excel/<int:exam_id>/', export_results_excel, name='export_results_excel'),
    path('filter_exams/', filter_exams, name='filter_exams'),
    # Exam overview and per-subject flow
    path('exam/<int:exam_id>/', exam_overview, name='exam_overview'),
    path('exam/<int:exam_id>/subject/<int:subject_id>/upload/', subject_upload, name='subject_upload'),
    path('exam/<int:exam_id>/subject/<int:subject_id>/pdf/', subject_pdf, name='subject_pdf'),
    path('exam/<int:exam_id>/subject/<int:subject_id>/approve/', approve_subject, name='approve_subject'),
    path('exam/<int:exam_id>/finalize/', finalize_exam, name='finalize_exam'),
    path('exam/<int:exam_id>/approve-all/', approve_exam_submissions, name='approve_exam_submissions'),
    # Roster upload (AJAX)
    path('upload-roster/', upload_roster, name='upload_roster'),
    # Academic dashboard & form results
    path('academic/', academic_dashboard, name='academic_dashboard'),
    path('form/<int:form_num>/results/', form_results, name='form_results'),
    path('form/<int:form_num>/excel/', form_results_excel, name='form_results_excel'),
    # School management
    path('school/', school_setup, name='school_setup'),
    path('school/<int:school_id>/subjects/', school_subjects, name='school_subjects'),
    path('school/<int:school_id>/create-exam/', create_exam_for_school, name='create_exam_for_school'),
    # Teacher dashboard
    path('teacher/', teacher_dashboard, name='teacher_dashboard'),
    # Speech entry
    path('speech/', speech_entry_page, name='speech_entry_page'),
    path('speech-sessions/', create_speech_session, name='create_speech_session'),
    path('speech-sessions/<int:session_id>/', speech_session_status, name='speech_session_status'),
    path('speech-sessions/<int:session_id>/ingest/', ingest_speech_entry, name='ingest_speech_entry'),
    path('speech-sessions/<int:session_id>/confirm/', confirm_speech_candidate, name='confirm_speech_candidate'),
    path('speech-sessions/<int:session_id>/finalize/', finalize_speech_session, name='finalize_speech_session'),
]
