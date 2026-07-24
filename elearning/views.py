from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count, Avg, Sum
from django.utils import timezone
from django.utils.text import slugify
from django.http import JsonResponse, HttpResponseForbidden, HttpResponseRedirect
from django.core.paginator import Paginator
from django.utils.http import url_has_allowed_host_and_scheme
import json

from .models import (
    Course, Module, Lesson, Enrollment, LessonProgress,
    Quiz, Question, QuizAttempt, QuizAnswer,
    Assignment, AssignmentSubmission,
    Discussion, DiscussionReply, Resource, CourseReview, Announcement,
    LearnerProfile,
)
from .forms import (
    CourseForm, ModuleForm, LessonForm, QuizForm, QuestionForm,
    AssignmentForm, AssignmentSubmissionForm, AssignmentGradingForm,
    DiscussionForm, DiscussionReplyForm, CourseReviewForm,
    LearnerProfileForm, AnnouncementForm,
)


# ── Helper: Get or create learner profile ──

def get_or_create_profile(user):
    profile, created = LearnerProfile.objects.get_or_create(
        user=user,
        defaults={'full_name': user.email.split('@')[0]}
    )
    return profile


# ── Home / Landing ──

def home(request):
    """Landing page showing featured courses."""
    featured = Course.objects.filter(is_published=True).annotate(
        total_lessons=Count('modules__lessons'),
        rating_avg=Avg('reviews__rating'),
    ).order_by('-enrollment_count', '-created_at')[:12]

    categories = Course.objects.filter(is_published=True) \
        .values('subject').annotate(count=Count('id')).order_by('-count')[:10]

    total_courses = Course.objects.filter(is_published=True).count()
    total_students = Enrollment.objects.count()
    total_lessons = Lesson.objects.filter(is_published=True, module__course__is_published=True).count()

    return render(request, 'elearning/home.html', {
        'featured': featured,
        'categories': categories,
        'total_courses': total_courses,
        'total_students': total_students,
        'total_lessons': total_lessons,
        'active_tab': 'home',
    })


# ── Course Listing ──

def course_list(request):
    """List all published courses with search and filter."""
    courses = Course.objects.filter(is_published=True).annotate(
        total_lessons=Count('modules__lessons', filter=Q(modules__lessons__is_published=True)),
        rating_avg=Avg('reviews__rating'),
        review_count=Count('reviews'),
    )

    search = request.GET.get('search', '')
    level = request.GET.get('level', '')
    subject = request.GET.get('subject', '')
    sort = request.GET.get('sort', '-created_at')

    if search:
        courses = courses.filter(
            Q(title__icontains=search) |
            Q(short_description__icontains=search) |
            Q(subject__icontains=search)
        )

    if level:
        courses = courses.filter(level=level)

    if subject:
        courses = courses.filter(subject=subject)

    if sort in ['title', '-title', 'created_at', '-created_at', 'enrollment_count', '-enrollment_count']:
        courses = courses.order_by(sort)
    else:
        courses = courses.order_by('-created_at')

    subjects = Course.objects.filter(is_published=True) \
        .values_list('subject', flat=True).distinct().exclude(subject='')

    paginator = Paginator(courses, 12)
    page = request.GET.get('page', 1)
    courses_page = paginator.get_page(page)

    return render(request, 'elearning/course_list.html', {
        'courses': courses_page,
        'subjects': sorted(set(subjects)),
        'search': search,
        'level': level,
        'subject': subject,
        'sort': sort,
        'active_tab': 'courses',
    })


# ── Course Detail ──

def course_detail(request, slug):
    """Show course detail with modules, lessons, and enrollment options."""
    course = get_object_or_404(Course, slug=slug)
    modules = Module.objects.filter(course=course).prefetch_related('lessons')
    lessons = Lesson.objects.filter(module__course=course, is_published=True)
    total_lessons = lessons.count()
    total_duration = lessons.aggregate(total=Sum('duration_minutes'))['total'] or 0

    is_enrolled = False
    enrollment = None
    if request.user.is_authenticated:
        enrollment = Enrollment.objects.filter(student=request.user, course=course).first()
        is_enrolled = enrollment is not None and enrollment.status != 'dropped'

    reviews = CourseReview.objects.filter(course=course).select_related('user')
    avg_rating = reviews.aggregate(avg=Avg('rating'))['avg'] or 0
    review_count = reviews.count()

    announcements = Announcement.objects.filter(course=course)[:5]
    discussions = Discussion.objects.filter(course=course)[:5]

    return render(request, 'elearning/course_detail.html', {
        'course': course,
        'modules': modules,
        'total_lessons': total_lessons,
        'total_duration': total_duration,
        'is_enrolled': is_enrolled,
        'enrollment': enrollment,
        'reviews': reviews[:10],
        'avg_rating': avg_rating,
        'review_count': review_count,
        'announcements': announcements,
        'discussions': discussions,
        'active_tab': 'courses',
    })


# ── Enrollment ──

@login_required
def enroll_course(request, slug):
    """Enroll the current user in a course."""
    course = get_object_or_404(Course, slug=slug)

    if not course.is_published:
        messages.error(request, "Samahani, kozi hii haijachapishwa bado.")
        return redirect('elearning:course_detail', slug=slug)

    enrollment, created = Enrollment.objects.get_or_create(
        student=request.user,
        course=course,
    )

    if created:
        course.enrollment_count = Enrollment.objects.filter(course=course, status='active').count()
        course.save(update_fields=['enrollment_count'])
        messages.success(request, f"Umefanikiwa kujiandikisha kwenye kozi ya \"{course.title}\"!")
    else:
        if enrollment.status == 'dropped':
            enrollment.status = 'active'
            enrollment.save(update_fields=['status'])
            messages.success(request, "Umejiandikisha tena kwenye kozi hii.")
        else:
            messages.info(request, "Tayari umejiandikisha kwenye kozi hii.")

    return redirect('elearning:course_detail', slug=slug)


# ── Lesson Viewing ──

@login_required
def lesson_detail(request, slug, lesson_id):
    """Show a lesson and mark progress."""
    course = get_object_or_404(Course, slug=slug)
    lesson = get_object_or_404(Lesson, id=lesson_id, module__course=course)

    enrollment = get_object_or_404(Enrollment, student=request.user, course=course)

    # Get all lessons for navigation
    all_lessons = Lesson.objects.filter(
        module__course=course, is_published=True
    ).select_related('module').order_by('module__order', 'order')

    # Find prev/next
    lesson_ids = list(all_lessons.values_list('id', flat=True))
    current_idx = lesson_ids.index(lesson.id) if lesson.id in lesson_ids else -1
    prev_lesson = Lesson.objects.filter(id=lesson_ids[current_idx - 1]).first() if current_idx > 0 else None
    next_lesson = Lesson.objects.filter(id=lesson_ids[current_idx + 1]).first() if current_idx < len(lesson_ids) - 1 else None

    # Mark progress
    progress, created = LessonProgress.objects.get_or_create(
        student=request.user,
        lesson=lesson,
    )
    if request.method == 'POST' and 'mark_complete' in request.POST:
        if not progress.is_completed:
            progress.is_completed = True
            progress.completed_at = timezone.now()
            progress.save()
            enrollment.update_progress()
            messages.success(request, "Somo limekamilika! ✓")

            # Check if course is completed
            if enrollment.status == 'completed':
                messages.success(request, f"Hongera! Umekamilisha kozi ya \"{course.title}\"!")

            if next_lesson:
                return redirect('elearning:lesson_detail', slug=slug, lesson_id=next_lesson.id)

        return redirect('elearning:lesson_detail', slug=slug, lesson_id=lesson.id)

    # Update last accessed
    enrollment.last_accessed = timezone.now()
    enrollment.save(update_fields=['last_accessed'])

    return render(request, 'elearning/lesson_detail.html', {
        'course': course,
        'lesson': lesson,
        'prev_lesson': prev_lesson,
        'next_lesson': next_lesson,
        'all_lessons': all_lessons,
        'progress': progress,
        'enrollment': enrollment,
    })


# ── Quiz Taking ──

@login_required
def quiz_take(request, slug, quiz_id):
    """Take a quiz."""
    course = get_object_or_404(Course, slug=slug)
    quiz = get_object_or_404(Quiz, id=quiz_id, course=course)
    enrollment = get_object_or_404(Enrollment, student=request.user, course=course)

    questions = Question.objects.filter(quiz=quiz).order_by('order', 'id')

    if not questions.exists():
        messages.warning(request, "Mtihani huu hauna maswali bado.")
        return redirect('elearning:course_detail', slug=slug)

    # Check attempt count
    previous_attempts = QuizAttempt.objects.filter(student=request.user, quiz=quiz).count()
    if previous_attempts >= quiz.max_attempts:
        messages.error(request, f"Umefikia kiwango cha juu cha majaribio ({quiz.max_attempts}).")
        return redirect('elearning:course_detail', slug=slug)

    if request.method == 'POST':
        score = 0
        total_points = quiz.total_points
        answers_data = []

        for question in questions:
            field_name = f'question_{question.id}'
            selected = request.POST.get(field_name, '')

            is_correct = False
            if question.question_type == 'multiple_choice':
                is_correct = selected == question.correct_answer
            elif question.question_type == 'true_false':
                is_correct = selected.lower() == question.correct_answer.lower()
            elif question.question_type == 'short_answer':
                is_correct = selected.strip().lower() == question.correct_answer.strip().lower()

            points_earned = question.points if is_correct else 0
            score += points_earned

            answers_data.append({
                'question': question,
                'selected': selected,
                'is_correct': is_correct,
                'points_earned': points_earned,
            })

        attempt_number = previous_attempts + 1
        percentage = round((score / total_points * 100), 2) if total_points > 0 else 0
        passed = percentage >= quiz.pass_percentage

        attempt = QuizAttempt.objects.create(
            student=request.user,
            quiz=quiz,
            attempt_number=attempt_number,
            score=score,
            total_points=total_points,
            percentage=percentage,
            passed=passed,
            completed_at=timezone.now(),
        )

        for q_data in answers_data:
            QuizAnswer.objects.create(
                attempt=attempt,
                question=q_data['question'],
                selected_answer=q_data['selected'],
                is_correct=q_data['is_correct'],
                points_earned=q_data['points_earned'],
            )

        messages.success(request, f"Mtihani umekamilika! Umepata {score}/{total_points} ({percentage}%).")
        return redirect('elearning:quiz_result', slug=slug, quiz_id=quiz.id, attempt_id=attempt.id)

    return render(request, 'elearning/quiz_take.html', {
        'course': course,
        'quiz': quiz,
        'questions': questions,
        'attempt_number': previous_attempts + 1,
        'max_attempts': quiz.max_attempts,
    })


@login_required
def quiz_result(request, slug, quiz_id, attempt_id):
    """Show quiz result."""
    course = get_object_or_404(Course, slug=slug)
    quiz = get_object_or_404(Quiz, id=quiz_id, course=course)
    attempt = get_object_or_404(QuizAttempt, id=attempt_id, student=request.user, quiz=quiz)
    answers = QuizAnswer.objects.filter(attempt=attempt).select_related('question')

    return render(request, 'elearning/quiz_result.html', {
        'course': course,
        'quiz': quiz,
        'attempt': attempt,
        'answers': answers,
    })


# ── Dashboard ──

@login_required
def dashboard(request):
    """Student dashboard showing enrolled courses and progress."""
    profile = get_or_create_profile(request.user)
    enrollments = Enrollment.objects.filter(
        student=request.user
    ).select_related('course').order_by('-last_accessed')

    completed_count = enrollments.filter(status='completed').count()
    active_count = enrollments.filter(status='active').count()
    total_lessons_completed = LessonProgress.objects.filter(
        student=request.user, is_completed=True
    ).count()
    total_quiz_attempts = QuizAttempt.objects.filter(student=request.user).count()

    return render(request, 'elearning/dashboard.html', {
        'profile': profile,
        'enrollments': enrollments,
        'completed_count': completed_count,
        'active_count': active_count,
        'total_lessons_completed': total_lessons_completed,
        'total_quiz_attempts': total_quiz_attempts,
        'active_tab': 'dashboard',
    })


# ── Teacher Dashboard ──

@login_required
def teacher_dashboard(request):
    """Teacher dashboard for managing courses."""
    profile = get_or_create_profile(request.user)

    # Check if user is a teacher
    if profile.role not in ['teacher', 'admin'] and not request.user.is_staff:
        messages.warning(request, "Sehemu hii ni ya walimu pekee.")
        return redirect('elearning:dashboard')

    courses = Course.objects.filter(created_by=request.user).annotate(
        student_count=Count('enrollments', filter=Q(enrollments__status='active')),
        lesson_count=Count('modules__lessons'),
    ).order_by('-created_at')

    # Get submissions needing grading
    pending_submissions = AssignmentSubmission.objects.filter(
        assignment__course__created_by=request.user,
        score__isnull=True
    ).select_related('assignment', 'student')[:20]

    return render(request, 'elearning/teacher_dashboard.html', {
        'profile': profile,
        'courses': courses,
        'pending_submissions': pending_submissions,
        'active_tab': 'teacher',
    })


# ── Course CRUD (Teacher) ──

@login_required
def course_create(request):
    """Create a new course."""
    if request.method == 'POST':
        form = CourseForm(request.POST, request.FILES)
        if form.is_valid():
            course = form.save(commit=False)
            course.created_by = request.user
            course.slug = slugify(course.title)
            # Ensure unique slug
            base_slug = course.slug
            counter = 1
            while Course.objects.filter(slug=course.slug).exists():
                course.slug = f"{base_slug}-{counter}"
                counter += 1
            course.save()
            messages.success(request, f"Kozi \"{course.title}\" imeundwa!")
            return redirect('elearning:course_manage', slug=course.slug)
    else:
        form = CourseForm()
    return render(request, 'elearning/course_form.html', {
        'form': form,
        'title': 'Unda Kozi Mpya',
        'submit_text': 'Unda Kozi',
        'active_tab': 'teacher',
    })


@login_required
def course_edit(request, slug):
    """Edit an existing course."""
    course = get_object_or_404(Course, slug=slug)
    if course.created_by != request.user and not request.user.is_staff:
        return HttpResponseForbidden("Hauruhusiwi kuhariri kozi hii.")

    if request.method == 'POST':
        form = CourseForm(request.POST, request.FILES, instance=course)
        if form.is_valid():
            form.save()
            messages.success(request, "Kozi imesasishwa!")
            return redirect('elearning:course_manage', slug=course.slug)
    else:
        form = CourseForm(instance=course)
    return render(request, 'elearning/course_form.html', {
        'form': form,
        'title': 'Hariri Kozi',
        'submit_text': 'Sasisha Kozi',
        'course': course,
        'active_tab': 'teacher',
    })


@login_required
def course_manage(request, slug):
    """Manage course content: modules, lessons, quizzes, assignments."""
    course = get_object_or_404(Course, slug=slug)
    if course.created_by != request.user and not request.user.is_staff:
        return HttpResponseForbidden("Hauruhusiwi kusimamia kozi hii.")

    modules = Module.objects.filter(course=course).prefetch_related('lessons')
    quizzes = Quiz.objects.filter(course=course)
    assignments = Assignment.objects.filter(course=course)
    enrollments = Enrollment.objects.filter(course=course).select_related('student')

    return render(request, 'elearning/course_manage.html', {
        'course': course,
        'modules': modules,
        'quizzes': quizzes,
        'assignments': assignments,
        'enrollments': enrollments,
        'active_tab': 'teacher',
    })


# ── Module CRUD ──

@login_required
def module_create(request, slug):
    course = get_object_or_404(Course, slug=slug)
    if course.created_by != request.user and not request.user.is_staff:
        return HttpResponseForbidden()
    if request.method == 'POST':
        form = ModuleForm(request.POST)
        if form.is_valid():
            module = form.save(commit=False)
            module.course = course
            module.save()
            messages.success(request, f"Moduli \"{module.title}\" imeundwa!")
            return redirect('elearning:course_manage', slug=slug)
    else:
        form = ModuleForm()
    return render(request, 'elearning/module_form.html', {
        'form': form, 'course': course, 'title': 'Unda Moduli Mpya',
        'active_tab': 'teacher',
    })


@login_required
def module_edit(request, slug, module_id):
    course = get_object_or_404(Course, slug=slug)
    module = get_object_or_404(Module, id=module_id, course=course)
    if course.created_by != request.user and not request.user.is_staff:
        return HttpResponseForbidden()
    if request.method == 'POST':
        form = ModuleForm(request.POST, instance=module)
        if form.is_valid():
            form.save()
            messages.success(request, "Moduli imesasishwa!")
            return redirect('elearning:course_manage', slug=slug)
    else:
        form = ModuleForm(instance=module)
    return render(request, 'elearning/module_form.html', {
        'form': form, 'course': course, 'module': module, 'title': 'Hariri Moduli',
        'active_tab': 'teacher',
    })


@login_required
def module_delete(request, slug, module_id):
    course = get_object_or_404(Course, slug=slug)
    module = get_object_or_404(Module, id=module_id, course=course)
    if course.created_by != request.user and not request.user.is_staff:
        return HttpResponseForbidden()
    if request.method == 'POST':
        module.delete()
        messages.success(request, "Moduli imefutwa.")
    return redirect('elearning:course_manage', slug=slug)


# ── Lesson CRUD ──

@login_required
def lesson_create(request, slug):
    course = get_object_or_404(Course, slug=slug)
    if course.created_by != request.user and not request.user.is_staff:
        return HttpResponseForbidden()
    if request.method == 'POST':
        form = LessonForm(request.POST, request.FILES)
        if form.is_valid():
            lesson = form.save()
            messages.success(request, f"Somo \"{lesson.title}\" limeundwa!")
            return redirect('elearning:course_manage', slug=slug)
    else:
        form = LessonForm()
        form.fields['module'].queryset = Module.objects.filter(course=course)
    return render(request, 'elearning/lesson_form.html', {
        'form': form, 'course': course, 'title': 'Unda Somo Jipya',
        'active_tab': 'teacher',
    })


@login_required
def lesson_edit(request, slug, lesson_id):
    course = get_object_or_404(Course, slug=slug)
    lesson = get_object_or_404(Lesson, id=lesson_id, module__course=course)
    if course.created_by != request.user and not request.user.is_staff:
        return HttpResponseForbidden()
    if request.method == 'POST':
        form = LessonForm(request.POST, request.FILES, instance=lesson)
        if form.is_valid():
            form.save()
            messages.success(request, "Somo limesasishwa!")
            return redirect('elearning:course_manage', slug=slug)
    else:
        form = LessonForm(instance=lesson)
        form.fields['module'].queryset = Module.objects.filter(course=course)
    return render(request, 'elearning/lesson_form.html', {
        'form': form, 'course': course, 'lesson': lesson, 'title': 'Hariri Somo',
        'active_tab': 'teacher',
    })


@login_required
def lesson_delete(request, slug, lesson_id):
    course = get_object_or_404(Course, slug=slug)
    lesson = get_object_or_404(Lesson, id=lesson_id, module__course=course)
    if course.created_by != request.user and not request.user.is_staff:
        return HttpResponseForbidden()
    if request.method == 'POST':
        lesson.delete()
        messages.success(request, "Somo limefutwa.")
    return redirect('elearning:course_manage', slug=slug)


# ── Quiz CRUD ──

@login_required
def quiz_create(request, slug):
    course = get_object_or_404(Course, slug=slug)
    if course.created_by != request.user and not request.user.is_staff:
        return HttpResponseForbidden()
    if request.method == 'POST':
        form = QuizForm(request.POST)
        if form.is_valid():
            quiz = form.save(commit=False)
            quiz.course = course
            quiz.save()
            messages.success(request, "Mtihani umeundwa!")
            return redirect('elearning:quiz_edit_questions', slug=slug, quiz_id=quiz.id)
    else:
        form = QuizForm()
        form.fields['module'].queryset = Module.objects.filter(course=course)
    return render(request, 'elearning/quiz_form.html', {
        'form': form, 'course': course, 'title': 'Unda Mtihani Mpya',
        'active_tab': 'teacher',
    })


@login_required
def quiz_edit(request, slug, quiz_id):
    course = get_object_or_404(Course, slug=slug)
    quiz = get_object_or_404(Quiz, id=quiz_id, course=course)
    if course.created_by != request.user and not request.user.is_staff:
        return HttpResponseForbidden()
    if request.method == 'POST':
        form = QuizForm(request.POST, instance=quiz)
        if form.is_valid():
            form.save()
            messages.success(request, "Mtihani umesasishwa!")
            return redirect('elearning:course_manage', slug=slug)
    else:
        form = QuizForm(instance=quiz)
        form.fields['module'].queryset = Module.objects.filter(course=course)
    return render(request, 'elearning/quiz_form.html', {
        'form': form, 'course': course, 'quiz': quiz, 'title': 'Hariri Mtihani',
        'active_tab': 'teacher',
    })


@login_required
def quiz_edit_questions(request, slug, quiz_id):
    """Add/edit questions for a quiz."""
    course = get_object_or_404(Course, slug=slug)
    quiz = get_object_or_404(Quiz, id=quiz_id, course=course)
    if course.created_by != request.user and not request.user.is_staff:
        return HttpResponseForbidden()

    questions = Question.objects.filter(quiz=quiz).order_by('order', 'id')

    if request.method == 'POST':
        form = QuestionForm(request.POST)
        if form.is_valid():
            question = form.save(commit=False)
            question.quiz = quiz
            question.save()
            messages.success(request, "Swali limeongezwa!")
            return redirect('elearning:quiz_edit_questions', slug=slug, quiz_id=quiz.id)
    else:
        form = QuestionForm()

    return render(request, 'elearning/quiz_questions.html', {
        'course': course,
        'quiz': quiz,
        'questions': questions,
        'form': form,
        'active_tab': 'teacher',
    })


@login_required
def question_delete(request, slug, quiz_id, question_id):
    course = get_object_or_404(Course, slug=slug)
    quiz = get_object_or_404(Quiz, id=quiz_id, course=course)
    question = get_object_or_404(Question, id=question_id, quiz=quiz)
    if course.created_by != request.user and not request.user.is_staff:
        return HttpResponseForbidden()
    if request.method == 'POST':
        question.delete()
        messages.success(request, "Swali limefutwa.")
    return redirect('elearning:quiz_edit_questions', slug=slug, quiz_id=quiz.id)


@login_required
def quiz_delete(request, slug, quiz_id):
    course = get_object_or_404(Course, slug=slug)
    quiz = get_object_or_404(Quiz, id=quiz_id, course=course)
    if course.created_by != request.user and not request.user.is_staff:
        return HttpResponseForbidden()
    if request.method == 'POST':
        quiz.delete()
        messages.success(request, "Mtihani umefutwa.")
    return redirect('elearning:course_manage', slug=slug)


# ── Assignment CRUD ──

@login_required
def assignment_create(request, slug):
    course = get_object_or_404(Course, slug=slug)
    if course.created_by != request.user and not request.user.is_staff:
        return HttpResponseForbidden()
    if request.method == 'POST':
        form = AssignmentForm(request.POST)
        if form.is_valid():
            assignment = form.save(commit=False)
            assignment.course = course
            if assignment.due_date:
                assignment.due_date = assignment.due_date
            assignment.save()
            messages.success(request, f"Kazi \"{assignment.title}\" imeundwa!")
            return redirect('elearning:course_manage', slug=slug)
    else:
        form = AssignmentForm()
        form.fields['module'].queryset = Module.objects.filter(course=course)
    return render(request, 'elearning/assignment_form.html', {
        'form': form, 'course': course, 'title': 'Unda Kazi Mpya',
        'active_tab': 'teacher',
    })


@login_required
def assignment_edit(request, slug, assignment_id):
    course = get_object_or_404(Course, slug=slug)
    assignment = get_object_or_404(Assignment, id=assignment_id, course=course)
    if course.created_by != request.user and not request.user.is_staff:
        return HttpResponseForbidden()
    if request.method == 'POST':
        form = AssignmentForm(request.POST, instance=assignment)
        if form.is_valid():
            form.save()
            messages.success(request, "Kazi imesasishwa!")
            return redirect('elearning:course_manage', slug=slug)
    else:
        form = AssignmentForm(instance=assignment)
        form.fields['module'].queryset = Module.objects.filter(course=course)
    return render(request, 'elearning/assignment_form.html', {
        'form': form, 'course': course, 'assignment': assignment, 'title': 'Hariri Kazi',
        'active_tab': 'teacher',
    })


@login_required
def assignment_delete(request, slug, assignment_id):
    course = get_object_or_404(Course, slug=slug)
    assignment = get_object_or_404(Assignment, id=assignment_id, course=course)
    if course.created_by != request.user and not request.user.is_staff:
        return HttpResponseForbidden()
    if request.method == 'POST':
        assignment.delete()
        messages.success(request, "Kazi imefutwa.")
    return redirect('elearning:course_manage', slug=slug)


# ── Assignment Submission ──

@login_required
def assignment_submit(request, slug, assignment_id):
    course = get_object_or_404(Course, slug=slug)
    assignment = get_object_or_404(Assignment, id=assignment_id, course=course)
    enrollment = Enrollment.objects.filter(student=request.user, course=course).first()
    if not enrollment:
        messages.error(request, "Lazima ujiandikishe kwenye kozi hii kwanza.")
        return redirect('elearning:course_detail', slug=slug)

    existing = AssignmentSubmission.objects.filter(assignment=assignment, student=request.user).first()
    if existing and existing.score is not None:
        messages.info(request, "Kazi yako tayari imekadiriwa.")
        return redirect('elearning:course_detail', slug=slug)

    is_late = assignment.is_past_due and not assignment.allow_late_submission
    if is_late and not existing:
        messages.error(request, "Samahani, muda wa kuwasilisha kazi hii umekwisha.")
        return redirect('elearning:course_detail', slug=slug)

    if request.method == 'POST':
        form = AssignmentSubmissionForm(request.POST, request.FILES, instance=existing)
        if form.is_valid():
            submission = form.save(commit=False)
            submission.assignment = assignment
            submission.student = request.user
            submission.is_late = assignment.is_past_due
            if not existing:
                submission.save()
            else:
                form.save()
            messages.success(request, "Kazi imewasilishwa!")
            return redirect('elearning:course_detail', slug=slug)
    else:
        form = AssignmentSubmissionForm(instance=existing)
    return render(request, 'elearning/assignment_submit.html', {
        'form': form, 'course': course, 'assignment': assignment, 'existing': existing,
        'active_tab': 'courses',
    })


# ── Assignment Grading ──

@login_required
def assignment_grade(request, slug, assignment_id, submission_id):
    course = get_object_or_404(Course, slug=slug)
    assignment = get_object_or_404(Assignment, id=assignment_id, course=course)
    if course.created_by != request.user and not request.user.is_staff:
        return HttpResponseForbidden()

    submission = get_object_or_404(AssignmentSubmission, id=submission_id, assignment=assignment)
    if request.method == 'POST':
        form = AssignmentGradingForm(request.POST, instance=submission)
        if form.is_valid():
            sub = form.save(commit=False)
            # Validate score does not exceed max points
            if sub.score is not None and sub.score > assignment.max_points:
                messages.error(request, f"Alama haziwezi kuzidi {assignment.max_points}.")
                return render(request, 'elearning/assignment_grade.html', {
                    'form': form, 'course': course, 'assignment': assignment, 'submission': submission,
                    'active_tab': 'teacher',
                })
            sub.graded_by = request.user
            sub.graded_at = timezone.now()
            sub.save()
            messages.success(request, "Kazi imekadiriwa!")
            return redirect('elearning:course_manage', slug=slug)
    else:
        form = AssignmentGradingForm(instance=submission)
    return render(request, 'elearning/assignment_grade.html', {
        'form': form, 'course': course, 'assignment': assignment, 'submission': submission,
        'active_tab': 'teacher',
    })


# ── Discussions ──

@login_required
def discussion_list(request, slug):
    course = get_object_or_404(Course, slug=slug)
    discussions = Discussion.objects.filter(course=course).select_related('user').annotate(
        reply_count=Count('replies')
    ).order_by('-is_pinned', '-created_at')

    return render(request, 'elearning/discussion_list.html', {
        'course': course,
        'discussions': discussions,
        'active_tab': 'courses',
    })


@login_required
def discussion_create(request, slug):
    course = get_object_or_404(Course, slug=slug)
    if request.method == 'POST':
        form = DiscussionForm(request.POST)
        if form.is_valid():
            discussion = form.save(commit=False)
            discussion.course = course
            discussion.user = request.user
            discussion.save()
            messages.success(request, "Mjadala umeanzishwa!")
            return redirect('elearning:discussion_list', slug=slug)
    else:
        form = DiscussionForm()
    return render(request, 'elearning/discussion_form.html', {
        'form': form, 'course': course, 'title': 'Anzisha Mjadala Mpya',
        'active_tab': 'courses',
    })


@login_required
def discussion_detail(request, slug, discussion_id):
    course = get_object_or_404(Course, slug=slug)
    discussion = get_object_or_404(Discussion, id=discussion_id, course=course)
    replies = DiscussionReply.objects.filter(discussion=discussion).select_related('user')

    if request.method == 'POST':
        form = DiscussionReplyForm(request.POST)
        if form.is_valid():
            reply = form.save(commit=False)
            reply.discussion = discussion
            reply.user = request.user
            reply.save()
            messages.success(request, "Jibu lako limeongezwa!")
            return redirect('elearning:discussion_detail', slug=slug, discussion_id=discussion.id)
    else:
        form = DiscussionReplyForm()
    return render(request, 'elearning/discussion_detail.html', {
        'course': course,
        'discussion': discussion,
        'replies': replies,
        'form': form,
        'active_tab': 'courses',
    })


# ── Course Review ──

@login_required
def add_review(request, slug):
    course = get_object_or_404(Course, slug=slug)
    enrollment = get_object_or_404(Enrollment, student=request.user, course=course)

    if request.method == 'POST':
        form = CourseReviewForm(request.POST)
        if form.is_valid():
            review, created = CourseReview.objects.update_or_create(
                course=course,
                user=request.user,
                defaults={
                    'rating': form.cleaned_data['rating'],
                    'comment': form.cleaned_data['comment'],
                }
            )
            # Update average rating
            avg = CourseReview.objects.filter(course=course).aggregate(avg=Avg('rating'))['avg'] or 0
            course.average_rating = round(avg, 2)
            course.save(update_fields=['average_rating'])
            messages.success(request, "Maoni yako yamehifadhiwa!")
    return redirect('elearning:course_detail', slug=slug)


# ── Announcements ──

@login_required
def announcement_create(request, slug):
    course = get_object_or_404(Course, slug=slug)
    if course.created_by != request.user and not request.user.is_staff:
        return HttpResponseForbidden()
    if request.method == 'POST':
        form = AnnouncementForm(request.POST)
        if form.is_valid():
            announcement = form.save(commit=False)
            announcement.course = course
            announcement.author = request.user
            announcement.save()
            messages.success(request, "Tangazo limechapishwa!")
            return redirect('elearning:course_manage', slug=slug)
    else:
        form = AnnouncementForm()
    return render(request, 'elearning/announcement_form.html', {
        'form': form, 'course': course, 'title': 'Chapisha Tangazo',
        'active_tab': 'teacher',
    })


# ── Profile ──

@login_required
def profile_edit(request):
    profile = get_or_create_profile(request.user)
    if request.method == 'POST':
        form = LearnerProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Wasifu wako umesasishwa!")
            return redirect('elearning:dashboard')
    else:
        form = LearnerProfileForm(instance=profile)
    return render(request, 'elearning/profile_form.html', {
        'form': form,
        'profile': profile,
        'active_tab': 'dashboard',
    })


# ── Language Switcher ──

def set_language(request):
    """Switch UI language between English and Swahili."""
    lang = request.GET.get('lang', 'en')
    next_url = request.GET.get('next', '/')
    # Prevent open redirect attacks
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=False):
        next_url = '/'
    if lang in ['en', 'sw']:
        request.session['ui_lang'] = lang
    return HttpResponseRedirect(next_url)


# ── Search ──

def search_courses(request):
    """JSON endpoint for search suggestions."""
    q = request.GET.get('q', '')
    if len(q) < 2:
        return JsonResponse({'results': []})
    courses = Course.objects.filter(
        is_published=True,
        title__icontains=q
    ).values('title', 'slug')[:10]
    return JsonResponse({'results': list(courses)})
