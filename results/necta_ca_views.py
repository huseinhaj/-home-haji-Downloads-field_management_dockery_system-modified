"""
necta_ca_views.py — NECTA Continuous Assessment Form (Form IV) automation.

Mwalimu/Academic anachagua:
  - Somo (Subject)
  - Exam ya kila column ya assessment (auto-mapped kwa exam_type, inaweza
    kubadilishwa kwa dropdowns)
  - Range ya alama (mf. 45-100) — mfumo unakadiria kwa uwiano wa wastani,
    performance-aware (mwanafunzi wa 80-100 hawezi kutiwa 60)
  - Center number + phone (header ya NECTA)

Preview inaonyeshwa kwenye ukurasa; Download inatengeneza Excel ya muundo
wa NECTA na kuhifadhi snapshot (ContinuousAssessmentSnapshot).
"""
import json
import logging

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from .models import ContinuousAssessmentSnapshot, Exam, SchoolSubject, Subject
from .permissions import teacher_or_academic_required
from .services.necta_ca_service import (
    COLUMN_KEYS,
    TERM_COLUMNS,
    auto_map_exams,
    build_ca_preview,
    generate_ca_excel,
)

logger = logging.getLogger(__name__)


def _school_subjects(school):
    return (Subject.objects
            .filter(schoolsubject__school=school)
            .distinct()
            .order_by('name'))


def _clean_params(school, payload):
    """Chuja + thibitisha params kutoka kwa payload (JSON au form-encoded)."""
    def _int(val, default):
        try:
            return int(val)
        except (TypeError, ValueError):
            return default

    subject_id = _int(payload.get('subject_id'), 0)
    subject = Subject.objects.filter(
        id=subject_id, schoolsubject__school=school,
    ).distinct().first()

    exam_map = {}
    for key in COLUMN_KEYS:
        exam_map[key] = _int(payload.get(f'exam_{key}'), 0) or None
    # Exam zote lazima ziwe za shule hii na Form 4
    valid_exam_ids = set(
        Exam.objects.filter(school=school, form=4)
        .values_list('id', flat=True)
    )
    exam_map = {
        k: (v if v in valid_exam_ids else None) for k, v in exam_map.items()
    }

    mark_min = _int(payload.get('mark_min'), 45)
    mark_max = _int(payload.get('mark_max'), 100)
    if mark_min < 0:
        mark_min = 0
    if mark_max > 100:
        mark_max = 100
    if mark_max <= mark_min:
        mark_min, mark_max = 45, 100   # fallback ya usalama

    year = _int(payload.get('year'), 0) or school.current_academic_year \
        or timezone.now().year
    center_no = (payload.get('center_no') or '').strip()[:20]
    phone = (payload.get('phone') or '').strip()[:30]

    return {
        'subject': subject,
        'exam_map': exam_map,
        'mark_min': mark_min,
        'mark_max': mark_max,
        'year': year,
        'center_no': center_no,
        'phone': phone,
    }


@teacher_or_academic_required
def necta_ca_form(request):
    """Ukurasa wa kutengeneza NECTA Continuous Assessment Form (Form IV).

    GET  → fomu ya kuchagua somo/exams/range
    POST (JSON, action=preview) → grid ya alama zilizokadiriwa (JSON)
    """
    school = request.user.school
    if not school:
        messages.error(request, "Hakuna shule iliyowekwa kwenye account yako.")
        return redirect('home')

    if school.is_primary:
        messages.error(
            request,
            "Fomu ya Continuous Assessment ya NECTA ni kwa shule za sekondari (Form IV).",
        )
        return redirect('home')

    # POST ya JSON — preview endpoint
    if request.method == 'POST' and request.content_type \
            and 'application/json' in request.content_type:
        try:
            payload = json.loads(request.body or b'{}')
        except (ValueError, json.JSONDecodeError):
            return JsonResponse({'error': 'Data si sahihi (JSON).'}, status=400)
        params = _clean_params(school, payload)
        if params['subject'] is None:
            return JsonResponse({'error': 'Chagua somo kwanza.'}, status=400)
        preview = build_ca_preview(
            school, params['subject'], params['exam_map'],
            params['mark_min'], params['mark_max'], params['year'],
        )
        preview['subject_name'] = params['subject'].name
        preview['year'] = params['year']
        return JsonResponse(preview)

    subjects = _school_subjects(school)
    form4_exams = list(Exam.objects.filter(school=school, form=4).order_by('year', 'id'))
    auto_map = auto_map_exams(form4_exams)

    # Annotate kila column na exam iliyochaguliwa na auto-map — Django
    # templates haziwezi kutafuta dict kwa dynamic key (auto_map[col.key]
    # hairuhusiwi), hivyo value huwekwa moja kwa moja kwenye column dict
    # ili dropdown zipate preselection sahihi.
    term_columns = [
        {**col, 'selected_exam_id': auto_map.get(col['key'])}
        for col in TERM_COLUMNS
    ]

    context = {
        'subjects': subjects,
        'form4_exams': form4_exams,
        'term_columns': term_columns,
        'default_year': school.current_academic_year or timezone.now().year,
        'snapshots': ContinuousAssessmentSnapshot.objects.filter(school=school)[:10],
    }
    return render(request, 'results/necta_ca_form.html', context)


@teacher_or_academic_required
def necta_ca_download(request):
    """Tengeneza Excel ya NECTA + hifadhi snapshot (history).

    Alama zinakadiriwa upya server-side kutoka params (tunaxiri rows
    za client) — hivyo faili linalo-download linalingana na DB.
    """
    school = request.user.school
    if not school:
        messages.error(request, "Hakuna shule iliyowekwa kwenye account yako.")
        return redirect('home')

    if request.method != 'POST':
        return redirect('necta_ca_form')

    if 'application/json' in (request.content_type or ''):
        try:
            payload = json.loads(request.body or b'{}')
        except (ValueError, json.JSONDecodeError):
            payload = {}
    else:
        payload = request.POST

    params = _clean_params(school, payload)
    if params['subject'] is None:
        messages.error(request, "Chagua somo kwanza kabla ya ku-download.")
        return redirect('necta_ca_form')

    preview = build_ca_preview(
        school, params['subject'], params['exam_map'],
        params['mark_min'], params['mark_max'], params['year'],
    )
    if not preview['rows']:
        messages.error(
            request,
            "Roster ya Form 4 haina wanafunzi — pakia orodha ya waliosajiliwa kwanza.",
        )
        return redirect('necta_ca_form')

    snapshot = ContinuousAssessmentSnapshot.objects.create(
        school=school,
        subject=params['subject'],
        subject_name=params['subject'].name,
        form=4,
        year=params['year'],
        params={
            'exam_map': {k: v for k, v in params['exam_map'].items()},
            'mark_min': params['mark_min'],
            'mark_max': params['mark_max'],
            'center_no': params['center_no'],
            'phone': params['phone'],
        },
        payload={
            'columns': preview['columns'],
            'rows': preview['rows'],
        },
        created_by=request.user if getattr(request.user, 'is_authenticated', False) else None,
    )
    logger.info(
        'necta_ca: snapshot %s created (school=%s subject=%s rows=%s)',
        snapshot.id, school.id, params['subject'].name, len(preview['rows']),
    )

    return generate_ca_excel(
        school, params['subject'].name, params['year'], preview['rows'],
        params['exam_map'], center_no=params['center_no'], phone=params['phone'],
    )
