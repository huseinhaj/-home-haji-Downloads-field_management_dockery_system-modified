from django.urls import path
from .pwa import pwa_manifest, pwa_service_worker
from .auth_views import results_login, results_logout, manage_teachers
from .billing_views import (
    choose_plan,
    pay_for_plan,
    payment_pending,
    payment_status_json,
    payment_webhook,
)
from .registration_views import (
    ajax_districts,
    ajax_schools,
    register_school_confirm,
    register_school_start,
)
from .views import (
    home,
    download_roster_template,
    upload_logos,
    upload_results,
    generate_results_pdf,
    export_results_excel,
    filter_exams,
    exam_overview,
    subject_upload,
    subject_pdf,
    subject_summary,
    finalize_exam,
    upload_roster,
    academic_dashboard,
    approve_subject,
    approve_exam_submissions,
    recompute_exam_results,
    return_submission,
    form_results,
    form_results_excel,
    school_setup,
    school_subjects,
    create_exam_for_school,
    teacher_dashboard,
    select_my_subjects,
    personal_upload,
    personal_upload_pdf,
    personal_upload_summary,
    student_result_public,
    public_results_search,
    exam_share_links,
    upload_form_students,
    delete_form_student,
    delete_all_form_students,
    assign_teacher_form,
    teacher_performance_report,
)
from .marks_entry import (
    download_scoresheet_names_pdf,
    marks_entry,
    marks_entry_save,
    marks_entry_submit,
    scoresheet_photo_extract,
)
from .speech_views import (
    confirm_speech_candidate,
    create_speech_session,
    finalize_speech_session,
    guided_voice_entry,
    ingest_speech_entry,
    speech_entry_page,
    speech_session_status,
    voice_entry_bulk_finalize,
    voice_entry_save_score,
    voice_entry_transcribe,
)

urlpatterns = [
    # PWA: Progressive Web App — manifest & service worker (scoped to /shule/)
    path('manifest.json', pwa_manifest, name='pwa_manifest'),
    path('sw.js', pwa_service_worker, name='pwa_service_worker'),
    # Results-app-only authentication (separate from field_app student login)
    path('ingia/', results_login, name='results_login'),
    path('toka/', results_logout, name='results_logout'),
    # Self-service registration: pick Region -> District -> School nationwide
    path('jiunge/', register_school_start, name='register_school_start'),
    path('jiunge/wilaya/', ajax_districts, name='ajax_districts'),
    path('jiunge/shule/', ajax_schools, name='ajax_schools'),
    path('jiunge/thibitisha/', register_school_confirm, name='register_school_confirm'),
    path('walimu/', manage_teachers, name='manage_teachers'),
    path('', home, name='home'),
    path('upload/', upload_results, name='upload_results'),
    path('results-pdf/<int:exam_id>/', generate_results_pdf, name='generate_results_pdf'),
    path('results-excel/<int:exam_id>/', export_results_excel, name='export_results_excel'),
    path('filter_exams/', filter_exams, name='filter_exams'),
    # Public results portal — search page (NECTA-style, no login)
    path('matokeo/', public_results_search, name='student_results_search'),
    # Public results lookup by token (NECTA-style, no login)
    path('matokeo/<uuid:token>/', student_result_public, name='student_result_public'),
    # Shareable links management (academic only)
    path('exam/<int:exam_id>/viungo/', exam_share_links, name='exam_share_links'),
    # Exam overview and per-subject flow
    path('exam/<int:exam_id>/', exam_overview, name='exam_overview'),
    path('exam/<int:exam_id>/subject/<int:subject_id>/upload/', subject_upload, name='subject_upload'),
    path('exam/<int:exam_id>/subject/<int:subject_id>/pdf/', subject_pdf, name='subject_pdf'),
    path('exam/<int:exam_id>/subject/<int:subject_id>/muhtasari/', subject_summary, name='subject_summary'),
    path('exam/<int:exam_id>/subject/<int:subject_id>/approve/', approve_subject, name='approve_subject'),
    path('exam/<int:exam_id>/subject/<int:subject_id>/return/', return_submission, name='return_submission'),
    path('exam/<int:exam_id>/finalize/', finalize_exam, name='finalize_exam'),
    path('exam/<int:exam_id>/approve-all/', approve_exam_submissions, name='approve_exam_submissions'),
    path('exam/<int:exam_id>/recompute/', recompute_exam_results, name='recompute_exam_results'),
    # Roster upload (AJAX)
    path('upload-roster/', upload_roster, name='upload_roster'),
    path('download-template/', download_roster_template, name='download_roster_template'),
    # Academic dashboard & form results
    path('academic/', academic_dashboard, name='academic_dashboard'),
    path('form/<int:form_num>/results/', form_results, name='form_results'),
    path('form/<int:form_num>/excel/', form_results_excel, name='form_results_excel'),
    # Logo upload for PDF header
    path('logos/', upload_logos, name='upload_logos'),
    # My school (each academic officer is scoped to exactly one school)
    path('school/', school_setup, name='school_setup'),
    path('school/masomo/', school_subjects, name='school_subjects'),
    path('school/unda-mtihani/', create_exam_for_school, name='create_exam_for_school'),
    # Teacher dashboard
    path('teacher/', teacher_dashboard, name='teacher_dashboard'),
    path('masomo-yangu/', select_my_subjects, name='select_my_subjects'),
    # Personal (binafsi) upload — private, not tied to any official exam
    path('binafsi/', personal_upload, name='personal_upload'),
    path('binafsi/<int:upload_id>/pdf/', personal_upload_pdf, name='personal_upload_pdf'),
    path('binafsi/<int:upload_id>/muhtasari/', personal_upload_summary, name='personal_upload_summary'),
    # Billing (ClickPesa mobile money subscription)
    path('malipo/', choose_plan, name='choose_plan'),
    path('malipo/lipa/<int:plan_id>/', pay_for_plan, name='pay_for_plan'),
    path('malipo/inasubiri/<int:transaction_id>/', payment_pending, name='payment_pending'),
    path('malipo/status/<int:transaction_id>/', payment_status_json, name='payment_status_json'),
    path('malipo/webhook/', payment_webhook, name='payment_webhook'),
    # Marks Entry — mbadala wa Speech Entry: pakia orodha → jaza alama → review → tuma
    path('marks/', marks_entry, name='marks_entry'),
    path('marks/save/', marks_entry_save, name='marks_entry_save'),
    path('marks/submit/', marks_entry_submit, name='marks_entry_submit'),
    path('marks/scoresheet-extract/', scoresheet_photo_extract, name='scoresheet_photo_extract'),
    path('marks/scoresheet-names-pdf/', download_scoresheet_names_pdf, name='download_scoresheet_names_pdf'),
    # Speech entry
    path('speech/', speech_entry_page, name='speech_entry_page'),
    # Guided voice entry — TTS reads name, teacher speaks score
    path('voice/', guided_voice_entry, name='guided_voice_entry'),
    path('voice/transcribe/', voice_entry_transcribe, name='voice_entry_transcribe'),
    path('voice/save/', voice_entry_save_score, name='voice_entry_save_score'),
    path('voice/finalize/', voice_entry_bulk_finalize, name='voice_entry_bulk_finalize'),
    path('speech-sessions/', create_speech_session, name='create_speech_session'),
    path('speech-sessions/<int:session_id>/', speech_session_status, name='speech_session_status'),
    path('speech-sessions/<int:session_id>/ingest/', ingest_speech_entry, name='ingest_speech_entry'),
    path('speech-sessions/<int:session_id>/confirm/', confirm_speech_candidate, name='confirm_speech_candidate'),
    path('speech-sessions/<int:session_id>/finalize/', finalize_speech_session, name='finalize_speech_session'),
    # Form student lists — Academic Officer uploads students per form
    path('form-students/', upload_form_students, name='upload_form_students'),
    path('form-students/<int:student_id>/delete/', delete_form_student, name='delete_form_student'),
    path('form-students/<int:form_num>/delete-all/', delete_all_form_students, name='delete_all_form_students'),
    # Assign teacher to form + subject
    path('assign-teacher/', assign_teacher_form, name='assign_teacher_form'),
    # Teacher performance report PDF — all teachers for a form
    path('report/form-<int:form_num>/teachers/', teacher_performance_report, name='teacher_performance_report'),
]
