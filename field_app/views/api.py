import json
from django.contrib.auth import get_user_model
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Count, F, Q
from django.db.models.functions import Greatest
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from field_app.decorators import assessor_login_required, board_login_required
from .models import (
    Assessor, School, SchoolAssignment, StudentTeacher,
    StudentAssessment, SchoolAssessment,
    StudentApplication, Region, RegionPin, SchoolPin,
    District, Subject, SchoolSubjectCapacity,
    LogbookEntry, AcademicYear,
    DistrictAllocation, SchoolAllocation,
)
# For schemes/lesson plan API views
try:
    from .models import EducationLevel, ClassLevel, Textbook
except ImportError:
    EducationLevel = None
    ClassLevel = None
    Textbook = None

from .utils import (
    _cached_active_year, get_current_academic_year,
    get_or_create_student_profile, invalidate_student_cache,
)

User = get_user_model()


@csrf_exempt
def ajax_search_schools(request):
    """AJAX endpoint for searching ALL schools"""
    search_query = request.GET.get('q', '').strip()

    if not search_query or len(search_query) < 2:
        return JsonResponse({'results': [], 'count': 0, 'error': 'Search term too short'})

    # Search in all schools
    schools = School.objects.filter(
        Q(name__icontains=search_query) |
        Q(district__name__icontains=search_query) |
        Q(district__region__name__icontains=search_query)
    ).select_related('district', 'district__region')[:100]

    results = []
    for school in schools:
        student_count = StudentTeacher.objects.filter(
            selected_school=school,
            approval_status='approved'
        ).count()

        assessor_count = SchoolAssessment.objects.filter(school=school).count()

        results.append({
            'id': school.id,
            'name': school.name,
            'district': school.district.name,
            'region': school.district.region.name,
            'level': school.level,
            'students': student_count,
            'assessors': assessor_count,
            'capacity': school.capacity,
            'current_students': school.current_students,
        })

    return JsonResponse({
        'results': results,
        'count': len(results),
        'search_term': search_query
    })

@staff_member_required
@csrf_exempt
def assessor_details_api(request, assessor_id):
    """API endpoint for assessor details"""
    if request.method == 'GET':
        assessor = get_object_or_404(Assessor, id=assessor_id)

        school_assignments = SchoolAssessment.objects.filter(assessor=assessor)
        schools_data = []
        for assignment in school_assignments:
            schools_data.append({
                'name': assignment.school.name,
                'district': assignment.school.district.name,
                'level': assignment.school.level,
                'assessment_date': assignment.assessment_date.strftime('%Y-%m-%d'),
            })

        data = {
            'id': assessor.id,
            'full_name': assessor.full_name,
            'email': assessor.email,
            'phone_number': assessor.phone_number,
            'is_active': assessor.is_active,
            'has_account': bool(assessor.user),
            'schools_count': len(schools_data),
            'schools': schools_data,
        }

        return JsonResponse(data)
    return JsonResponse({'error': 'Invalid method'}, status=405)


@login_required
def api_confirm_change_school(request):
    """API endpoint to confirm school change - SIMPLE WORKING VERSION"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
        new_school_id = data.get('school_id')
    except:
        return JsonResponse({'error': 'Invalid data'}, status=400)

    if not new_school_id:
        return JsonResponse({'error': 'School ID required'}, status=400)

    student = get_or_create_student_profile(request.user)

    # Check if student can change school
    if not student.selected_school:
        return JsonResponse({'error': 'No school selected'}, status=400)

    CAN_CHANGE_DAYS = 7
    approved_app = StudentApplication.objects.filter(
        student=student, status='approved'
    ).select_related('subject', 'school').first()

    if approved_app and approved_app.approval_date:
        days_passed = (timezone.now() - approved_app.approval_date).days
        if days_passed > CAN_CHANGE_DAYS:
            return JsonResponse({
                'error': f'Muda wa kubadili shule umekwisha. Ungeweza kubadili ndani ya siku {CAN_CHANGE_DAYS} baada ya kuidhinishwa.'
            }, status=403)
    else:
        # No approved app — use initial selection date window
        if not student.initial_school_selection_date:
            student.initial_school_selection_date = timezone.now()
            student.save()
            invalidate_student_cache(student)
        days_passed = (timezone.now() - student.initial_school_selection_date).days
        if days_passed > CAN_CHANGE_DAYS:
            return JsonResponse({'error': f'Muda wa kubadili shule umekwisha (siku {CAN_CHANGE_DAYS} tu).'}, status=400)

    try:
        new_school = School.objects.get(id=new_school_id)
        old_school = student.selected_school

        # Check capacity
        if new_school.current_students >= new_school.capacity:
            return JsonResponse({'error': f'Shule {new_school.name} imejaa'}, status=400)

        # Check if pinned
        current_year = get_current_academic_year()
        is_pinned = SchoolPin.objects.filter(
            school=new_school,
            academic_year=current_year,
            is_pinned=True
        ).exists()

        if is_pinned:
            return JsonResponse({'error': f'Shule {new_school.name} haipatikani'}, status=400)

        from django.db import transaction
        with transaction.atomic():
            # If student had an approved application, remove it and release capacity
            if approved_app:
                if approved_app.subject:
                    SchoolSubjectCapacity.objects.filter(
                        school=old_school, subject=approved_app.subject
                    ).update(current_students=Greatest(F('current_students') - 1, 0))
                approved_app.delete()
                student.subjects.clear()

            # Decrement old school, increment new school
            School.objects.filter(id=old_school.id).update(
                current_students=Greatest(F('current_students') - 1, 0)
            )
            School.objects.filter(id=new_school.id).update(
                current_students=F('current_students') + 1
            )

            # Delete any remaining pending applications for old school
            StudentApplication.objects.filter(
                student=student, school=old_school, status='pending'
            ).delete()

            # Update student
            student.selected_school = new_school
            student.school_change_count = F('school_change_count') + 1
            student.last_school_change_date = timezone.now()
            student.save()
            invalidate_student_cache(student)

        print(f"✅ SUCCESS: {student.full_name} changed from {old_school.name} to {new_school.name}")

        redirect_url = f'/select-subjects/{new_school.id}/' if approved_app else '/dashboard/'
        return JsonResponse({
            'success': True,
            'message': f'Umebadilishwa hadi {new_school.name}. Chagua masomo mapya.',
            'redirect_url': redirect_url,
        })

    except School.DoesNotExist:
        return JsonResponse({'error': 'School not found'}, status=404)
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def api_get_schools_for_change(request):
    """API endpoint for getting schools by district - FAST with caching"""

    student = get_or_create_student_profile(request.user)

    if not student.selected_school:
        return JsonResponse({'error': 'No school selected'}, status=400)

    # Get parameters
    district_id = request.GET.get('district_id')
    level = request.GET.get('level', 'Secondary')
    search = request.GET.get('search', '').strip()
    page = int(request.GET.get('page', 1))
    per_page = 12  # Schools per page

    # Validate district
    if not district_id:
        return JsonResponse({'error': 'District ID required'}, status=400)

    try:
        district = District.objects.get(id=district_id)
    except District.DoesNotExist:
        return JsonResponse({'error': 'District not found'}, status=404)

    # Get current academic year for pinned schools
    current_year = get_current_academic_year()

    # Get pinned school IDs (cache for 5 minutes)
    from django.core.cache import cache
    cache_key = f'pinned_schools_{current_year.id if current_year else "none"}'
    pinned_school_ids = cache.get(cache_key)
    if pinned_school_ids is None and current_year:
        pinned_school_ids = list(SchoolPin.objects.filter(
            academic_year=current_year,
            is_pinned=True
        ).values_list('school_id', flat=True))
        cache.set(cache_key, pinned_school_ids, 300)  # Cache for 5 minutes
    elif not current_year:
        pinned_school_ids = []

    # Base queryset - only schools in selected district
    schools_qs = School.objects.filter(
        district_id=district_id,
        level=level
    ).exclude(id=student.selected_school.id)

    # Exclude pinned schools
    if pinned_school_ids:
        schools_qs = schools_qs.exclude(id__in=pinned_school_ids)

    # Exclude full schools
    schools_qs = schools_qs.filter(current_students__lt=F('capacity'))

    # Apply search filter
    if search:
        schools_qs = schools_qs.filter(
            Q(name__icontains=search) |
            Q(district__name__icontains=search) |
            Q(district__region__name__icontains=search)
        )

    # Select related for efficiency
    schools_qs = schools_qs.select_related('district', 'district__region')

    # Count total (for pagination)
    total_count = schools_qs.count()

    # Apply pagination
    start = (page - 1) * per_page
    end = start + per_page
    schools = schools_qs[start:end]

    # Prepare data
    schools_data = []
    for school in schools:
        # Calculate occupancy
        if school.capacity > 0:
            occupancy = round((school.current_students / school.capacity) * 100)
            occupancy = 0

        schools_data.append({
            'id': school.id,
            'name': school.name,
            'district': school.district.name,
            'region': school.district.region.name,
            'level': school.level,
            'current_students': school.current_students,
            'capacity': school.capacity,
            'available_spots': school.capacity - school.current_students,
            'occupancy_percentage': occupancy,
            'is_available': school.current_students < school.capacity,
        })

    return JsonResponse({
        'success': True,
        'schools': schools_data,
        'total': total_count,
        'page': page,
        'total_pages': (total_count + per_page - 1) // per_page,
        'has_next': end < total_count,
        'has_previous': page > 1,
    })

@login_required
def get_classes_by_level(request):
    """AJAX endpoint to get classes based on education level"""
    level_id = request.GET.get('level_id')
    if level_id:
        classes = ClassLevel.objects.filter(education_level_id=level_id).values('id', 'name')
        return JsonResponse(list(classes), safe=False)
    return JsonResponse([], safe=False)

@login_required
def get_subjects_by_level(request):
    """AJAX endpoint to get subjects based on education level"""
    level_id = request.GET.get('level_id')
    if level_id:
        try:
            education_level = EducationLevel.objects.get(id=level_id)
            level_name = education_level.name.lower()

            # Filter subjects based on education level
            if 'primary' in level_name:
                subjects = Subject.objects.filter(level='primary')
            elif 'ordinary' in level_name or 'secondary' in level_name:
                subjects = Subject.objects.filter(level='secondary')
                subjects = Subject.objects.all()

            return JsonResponse(list(subjects.values('id', 'name')), safe=False)
        except:
            return JsonResponse([], safe=False)
    return JsonResponse([], safe=False)

@login_required
def get_textbooks_by_level(request):
    """AJAX endpoint to get textbooks based on education level"""
    level_id = request.GET.get('level_id')
    if level_id:
        try:
            education_level = EducationLevel.objects.get(id=level_id)
            textbooks = Textbook.objects.filter(
                education_level=education_level.name.lower(),
                is_active=True
            ).values('id', 'title')
            return JsonResponse(list(textbooks), safe=False)
        except:
            return JsonResponse([], safe=False)
    return JsonResponse([], safe=False)

def api_get_schools(request):
    """API endpoint for AJAX school search"""
    district_id = request.GET.get('district_id')
    level = request.GET.get('level', 'Secondary')
    query = request.GET.get('q', '').strip()

    if not district_id:
        return JsonResponse({'success': False, 'error': 'District ID required'})

    district = get_object_or_404(District, id=district_id)
    current_year = get_current_academic_year()

    # Get pinned schools
    pinned_school_ids = []
    if current_year:
        pinned_school_ids = list(SchoolPin.objects.filter(
            academic_year=current_year,
            is_pinned=True
        ).values_list('school_id', flat=True))

    # Base queryset
    schools_qs = School.objects.filter(district=district, level=level)

    if query:
        schools_qs = schools_qs.filter(name__icontains=query)

    # Process schools
    schools_data = []
    available_count = 0
    pinned_count = 0
    full_count = 0

    for school in schools_qs:
        is_pinned = school.id in pinned_school_ids
        is_selectable = (not is_pinned) and (school.current_students < school.capacity)

        if is_pinned:
            pinned_count += 1
        elif not is_selectable:
            full_count += 1
            available_count += 1

        occupancy = round((school.current_students / school.capacity) * 100) if school.capacity > 0 else 0

        schools_data.append({
            'id': school.id,
            'name': school.name,
            'level': school.level,
            'level_display': school.get_level_display(),
            'current_students': school.current_students,
            'capacity': school.capacity,
            'occupancy_percentage': occupancy,
            'is_pinned': is_pinned,
            'is_selectable': is_selectable,
        })

    return JsonResponse({
        'success': True,
        'schools': schools_data,
        'total_schools': schools_qs.count(),
        'available_schools': available_count,
        'pinned_schools': pinned_count,
        'full_schools': full_count,
    })

@login_required
def api_select_school_temp(request):
    """Temporarily store selected school in session"""
    if request.method == 'POST':
        data = json.loads(request.body)
        school_id = data.get('school_id')
        if school_id:
            request.session['temp_selected_school_id'] = school_id
            return JsonResponse({'success': True})
    return JsonResponse({'success': False})

def api_districts_by_region(request):
    """Return districts for a given region - used in admin BoardMember form"""
    region_id = request.GET.get('region_id')
    if not region_id:
        return JsonResponse([], safe=False)
    districts = District.objects.filter(region_id=region_id).order_by('name').values('id', 'name')
    return JsonResponse(list(districts), safe=False)


def api_clear_selected_school(request):
    """Clear selected school from session"""
    if request.method == 'POST':
        request.session.pop('temp_selected_school', None)
        return JsonResponse({'success': True})
    return JsonResponse({'success': False})

@login_required
def api_filter_schools(request):
    """API endpoint for filtering schools - shows only selected school"""
    district_id = request.GET.get('district_id')
    selected_school_id = request.GET.get('selected_school_id')

    if not district_id:
        return JsonResponse({'success': False, 'error': 'District ID required'})

    district = get_object_or_404(District, id=district_id)
    current_year = get_current_academic_year()

    # Get pinned schools
    pinned_school_ids = []
    if current_year:
        pinned_school_ids = list(SchoolPin.objects.filter(
            academic_year=current_year,
            is_pinned=True
        ).values_list('school_id', flat=True))

    # Get all schools first
    schools_qs = School.objects.filter(district=district)

    # If selected_school_id is provided, show ONLY that school
    if selected_school_id:
        schools_qs = schools_qs.filter(id=selected_school_id)

    schools_data = []
    for school in schools_qs:
        is_pinned = school.id in pinned_school_ids
        is_selectable = (not is_pinned) and (school.current_students < school.capacity)
        occupancy = round((school.current_students / school.capacity) * 100) if school.capacity > 0 else 0

        schools_data.append({
            'id': school.id,
            'name': school.name,
            'level': school.level,
            'level_display': school.get_level_display(),
            'current_students': school.current_students,
            'capacity': school.capacity,
            'occupancy_percentage': occupancy,
            'is_pinned': is_pinned,
            'is_selectable': is_selectable,
        })

    return JsonResponse({
        'success': True,
        'schools': schools_data,
        'total_schools': schools_qs.count(),
    })
