from django.urls import path
from . import views

app_name = 'elearning'

urlpatterns = [
    # Language
    path('set-language/', views.set_language, name='set_language'),

    # Home
    path('', views.home, name='home'),

    # Courses
    path('courses/', views.course_list, name='course_list'),
    path('course/<slug:slug>/', views.course_detail, name='course_detail'),
    path('course/<slug:slug>/enroll/', views.enroll_course, name='enroll_course'),

    # Lessons
    path('course/<slug:slug>/lesson/<int:lesson_id>/', views.lesson_detail, name='lesson_detail'),

    # Quizzes
    path('course/<slug:slug>/quiz/<int:quiz_id>/', views.quiz_take, name='quiz_take'),
    path('course/<slug:slug>/quiz/<int:quiz_id>/result/<int:attempt_id>/', views.quiz_result, name='quiz_result'),

    # Assignments
    path('course/<slug:slug>/assignment/<int:assignment_id>/submit/', views.assignment_submit, name='assignment_submit'),
    path('course/<slug:slug>/assignment/<int:assignment_id>/grade/<int:submission_id>/', views.assignment_grade, name='assignment_grade'),

    # Discussions
    path('course/<slug:slug>/discussions/', views.discussion_list, name='discussion_list'),
    path('course/<slug:slug>/discussions/new/', views.discussion_create, name='discussion_create'),
    path('course/<slug:slug>/discussions/<int:discussion_id>/', views.discussion_detail, name='discussion_detail'),

    # Reviews
    path('course/<slug:slug>/review/', views.add_review, name='add_review'),

    # Dashboards
    path('dashboard/', views.dashboard, name='dashboard'),
    path('teacher/', views.teacher_dashboard, name='teacher_dashboard'),

    # Profile
    path('profile/edit/', views.profile_edit, name='profile_edit'),

    # Teacher: Course Management
    path('teacher/course/new/', views.course_create, name='course_create'),
    path('teacher/course/<slug:slug>/edit/', views.course_edit, name='course_edit'),
    path('teacher/course/<slug:slug>/manage/', views.course_manage, name='course_manage'),

    # Teacher: Modules
    path('teacher/course/<slug:slug>/module/new/', views.module_create, name='module_create'),
    path('teacher/course/<slug:slug>/module/<int:module_id>/edit/', views.module_edit, name='module_edit'),
    path('teacher/course/<slug:slug>/module/<int:module_id>/delete/', views.module_delete, name='module_delete'),

    # Teacher: Lessons
    path('teacher/course/<slug:slug>/lesson/new/', views.lesson_create, name='lesson_create'),
    path('teacher/course/<slug:slug>/lesson/<int:lesson_id>/edit/', views.lesson_edit, name='lesson_edit'),
    path('teacher/course/<slug:slug>/lesson/<int:lesson_id>/delete/', views.lesson_delete, name='lesson_delete'),

    # Teacher: Quizzes
    path('teacher/course/<slug:slug>/quiz/new/', views.quiz_create, name='quiz_create'),
    path('teacher/course/<slug:slug>/quiz/<int:quiz_id>/edit/', views.quiz_edit, name='quiz_edit'),
    path('teacher/course/<slug:slug>/quiz/<int:quiz_id>/questions/', views.quiz_edit_questions, name='quiz_edit_questions'),
    path('teacher/course/<slug:slug>/quiz/<int:quiz_id>/question/<int:question_id>/delete/', views.question_delete, name='question_delete'),
    path('teacher/course/<slug:slug>/quiz/<int:quiz_id>/delete/', views.quiz_delete, name='quiz_delete'),

    # Teacher: Assignments
    path('teacher/course/<slug:slug>/assignment/new/', views.assignment_create, name='assignment_create'),
    path('teacher/course/<slug:slug>/assignment/<int:assignment_id>/edit/', views.assignment_edit, name='assignment_edit'),
    path('teacher/course/<slug:slug>/assignment/<int:assignment_id>/delete/', views.assignment_delete, name='assignment_delete'),

    # Teacher: Announcements
    path('teacher/course/<slug:slug>/announcement/new/', views.announcement_create, name='announcement_create'),

    # Search API
    path('api/search/', views.search_courses, name='search_courses'),
]
