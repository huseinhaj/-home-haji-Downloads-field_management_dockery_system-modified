from django.contrib.auth import views as auth_views
from django.urls import path
from . import views

urlpatterns = [
    # =========================
    path('', views.homepage, name='homepage'),
    path('password_reset/', auth_views.PasswordResetView.as_view(), name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(), name='password_reset_complete'),
    # =========================
    # CORE PAGES
    path('dashboard/', views.dashboard, name='dashboard'),
    path('monthly-report/<int:report_id>/', views.student_monthly_report, name='student_monthly_report'),
    path('register/', views.register, name='register'),
    # urls.py
    path('login/', views.login_view, name='login'),  #  # Name ni 'login' sasa
    path('logout/', views.logout_view, name='logout'),

    # =========================
    # SCHOOL SELECTION
    # =========================
    path('select-region/', views.select_region, name='select_region'),
    path('select-district/<int:region_id>/', views.select_district, name='select_district'),
    path('select-school/<int:district_id>/', views.select_school, name='select_school'),
    
    # =========================
    # SUBJECT SELECTION
    # =========================
    path('select-subjects/<int:school_id>/', views.select_subjects, name='select_subjects'),
    path('apply-subject/<int:subject_id>/<int:school_id>/', views.apply_for_subject, name='apply_for_subject'),
    path('change-school/', views.change_school, name='change_school'),
    path('api/schools-for-change/', views.api_get_schools_for_change, name='api_schools_for_change'),
    path('api/confirm-change-school/', views.api_confirm_change_school, name='api_confirm_change_school'),
    #path('select-school-for-change/', views.select_school_for_change, name='select_school_for_change'),
    # =========================
    # LOGBOOK
    # =========================
    path('submit-logbook/', views.submit_logbook, name='submit_logbook'),
    path('logbook-history/', views.logbook_history, name='logbook_history'),
    path('logbook/download/<str:period_type>/', views.download_logbook_pdf, name='download_logbook_pdf'),
    # =========================
# LOGBOOK - REKEBISHWA: ADD MISSING URL
    path('assessor/password-reset/', views.assessor_password_reset, name='assessor_password_reset'),
    path('assessor/password-reset/done/', views.assessor_password_reset_done, name='assessor_password_reset_done'),
# =========================
    path('logbook/download-options/', views.logbook_download_options, name='logbook_download_options'), 
    # =========================
    # ADMIN MANAGEMENT PAGES - USE DIFFERENT PREFIX
    # =========================
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('management/approve-application/<int:application_id>/', views.approve_application, name='approve_application'),
    path('management/assign-assessor/', views.assign_assessor, name='assign_assessor'),  # 🔥 SAHIHI SASA
    path('management/bulk-assign-assessors/', views.bulk_assign_assessors, name='bulk_assign_assessors'),
    
    # =========================
    # REGION PINNING
    # =========================
    # Add these URLs

    path('manage-regions/', views.manage_regions, name='manage_regions'),
    path('toggle-region-pin/<int:region_id>/', views.toggle_region_pin, name='toggle_region_pin'),
    path('change-academic-year/', views.change_academic_year, name='change_academic_year'),
    path('create-academic-year/', views.create_academic_year, name='create_academic_year'),
    path('reset-all-region-pins/', views.reset_all_region_pins, name='reset_all_region_pins'),
    path('pin-regions/', views.region_pinning_view, name='pin_regions'),
    path('pinning-success/', views.pinning_success_view, name='pinning_success'),
    
    # =========================
    # APPROVAL LETTERS
    # =========================
    path('download-individual-letter/', views.download_individual_letter, name='download_individual_letter'),
    path('download-group-letter/', views.download_group_letter, name='download_group_letter'),
    
    # =========================
    # ASSESSOR PAGES
    # =========================
    path('assessor/login/', views.assessor_login, name='assessor_login'),
    path('assessor/dashboard/', views.assessor_dashboard, name='assessor_dashboard'),
    
    # =========================
    # STUDENT PAGES
    # =========================
    
    path('my-assessors/', views.my_assessors, name='my_assessors'),
    path('profile/create/', views.profile_create, name='profile_create'),
       path('assessor/bulk-assign/', views.bulk_assign_assessors, name='bulk_assign_assessors'),
    path('assessor/bulk-results/', views.bulk_assignment_results, name='bulk_assignment_results'),
    path('assessor/list/', views.assessor_list, name='assessor_list'),
    #path('assessor/resend-credentials/', views.resend_credentials, name='resend_credentials'),
    path('field/ajax-search-schools/', views.ajax_search_schools, name='ajax_search_schools'),
    # API endpoints
    path('assessor/school/<int:school_id>/students/', views.assessor_student_detail, name='assessor_student_detail'),
    path('assessor/student/<int:student_id>/assessment/', views.assessor_student_assessment, name='assessor_student_assessment'),
    path('assessor/logbook/<int:entry_id>/remark/', views.assessor_add_logbook_remark, name='assessor_add_logbook_remark'),
    path('api/assessor/<int:assessor_id>/details/', views.assessor_details_api, name='assessor_details_api'),
    #path('api/assessor/<int:assessor_id>/resend-credentials/', views.resend_assessor_credentials_api, name='resend_assessor_credentials_api'),
    #path('api/send-test-email/', views.send_test_email_api, name='send_test_email'),
    path('generate-scheme/', views.generate_scheme_view, name='generate_scheme'),
    path('ajax-generate-scheme/', views.ajax_generate_scheme, name='ajax_generate_scheme'),
    path('download-scheme-pdf/', views.download_scheme_pdf, name='download_scheme_pdf'),
    path('download-scheme-word/', views.download_scheme_word, name='download_scheme_word'),
    path('admin-report-pdf/', views.admin_report_pdf, name='admin_report_pdf'),
    path('get-classes/', views.get_classes_by_level, name='get_classes'),
    path('get-subjects-by-level/', views.get_subjects_by_level, name='get_subjects_by_level'),
    path('get-textbooks/', views.get_textbooks_by_level, name='get_textbooks'),
    # Lesson Plan URLs
    path('lesson-plan/', views.lesson_plan_view, name='lesson_plan'),
    path('ajax-generate-lessonplan/', views.ajax_generate_lessonplan, name='ajax_generate_lessonplan'),
    path('download-lesson-plan-pdf/', views.download_lesson_plan_pdf, name='download_lesson_plan_pdf'),
    path('download-lesson-plan-word/', views.download_lesson_plan_word, name='download_lesson_plan_word'),
    path('api/get-schools/', views.api_get_schools, name='api_get_schools'),
    path('api/select-school-temp/', views.api_select_school_temp, name='api_select_school_temp'),
    path('api/clear-selected-school/', views.api_clear_selected_school, name='api_clear_selected_school'),
    path('create-admin/', views.create_admin, name='create_admin'),
    path('set-language/', views.set_language, name='set_language'),

    # =========================
    # BODI YA WALIMU — Teacher Board
    # =========================
    path('board/login/', views.board_login, name='board_login'),
    path('board/logout/', views.board_logout, name='board_logout'),
    path('board/', views.board_home, name='board_home'),
    path('board/region/<int:region_id>/', views.board_district_list, name='board_district_list'),
    path('board/district/<int:district_id>/', views.board_school_list, name='board_school_list'),
    path('board/district/<int:district_id>/report/', views.board_deo_report, name='board_deo_report'),
    path('board/student/<int:student_id>/', views.board_student_progress, name='board_student_progress'),
    path('board/comment/add/', views.board_add_comment, name='board_add_comment'),
    path('create-board-member/', views.create_board_member, name='create_board_member'),
]
