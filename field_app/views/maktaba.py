"""
MAKTABA — views
===============
Ukurasa wa maktaba ya notes na mitihani zilizochotwa automatic kutoka
sites za nje (Wazaelimu, Lusa Elimu, Mitihani, Elimu Zone), zenye
uainishaji wa AI, muhtasari, filters na download.
"""
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from ..models import MaterialSource, ScrapedMaterial

TYPE_LABELS = {
    'notes': 'Notes',
    'exam': 'Mitihani',
    'book': 'Vitabu (TIE)',
    'syllabus': 'Syllabus',
    'other': 'Nyingine',
}
LEVEL_LABELS = {
    'primary': 'Primary',
    'ordinary': 'O-Level',
    'advanced': 'A-Level',
    'technical': 'Technical/VETA',
}


@login_required
def maktaba(request):
    mats = ScrapedMaterial.objects.filter(published=True).select_related('source', 'subject')

    q = (request.GET.get('q') or '').strip()
    mtype = request.GET.get('type') or ''
    level = request.GET.get('level') or ''
    klass = (request.GET.get('class') or '').strip()
    subject = (request.GET.get('subject') or '').strip()

    if q:
        mats = mats.filter(
            Q(title__icontains=q) | Q(ai_summary__icontains=q)
            | Q(subject_name__icontains=q))
    if mtype in TYPE_LABELS:
        mats = mats.filter(material_type=mtype)
    if level in LEVEL_LABELS:
        mats = mats.filter(education_level=level)
    if klass:
        mats = mats.filter(class_name__iexact=klass)
    if subject:
        mats = mats.filter(Q(subject__name__iexact=subject) | Q(subject_name__iexact=subject))

    sort = request.GET.get('sort') or 'new'
    mats = mats.order_by('-downloads' if sort == 'top' else '-created_at')

    paginator = Paginator(mats, 24)
    page_obj = paginator.get_page(request.GET.get('page'))

    # filter chips data
    classes = (ScrapedMaterial.objects.filter(published=True)
               .exclude(class_name='').values_list('class_name', flat=True)
               .distinct().order_by('class_name'))
    subjects = (ScrapedMaterial.objects.filter(published=True)
                .exclude(subject_name='').values_list('subject_name', flat=True)
                .distinct().order_by('subject_name'))

    ctx = {
        'page_obj': page_obj,
        'materials': page_obj.object_list,
        'type_labels': TYPE_LABELS,
        'level_labels': LEVEL_LABELS,
        'classes': classes,
        'subjects': subjects,
        'filters': {
            'q': q, 'type': mtype, 'level': level, 'class': klass,
            'subject': subject, 'sort': sort,
        },
        'total': ScrapedMaterial.objects.filter(published=True).count(),
        'sources': MaterialSource.objects.filter(enabled=True),
        'last_run': None,
    }
    from ..models import MaterialImportRun
    last = MaterialImportRun.objects.first()
    if last:
        ctx['last_run'] = last

    return render(request, 'field_app/maktaba.html', ctx)


@login_required
def maktaba_download(request, material_id):
    mat = ScrapedMaterial.objects.filter(id=material_id, published=True).first()
    if not mat:
        return HttpResponse('Faili haipatikani.', status=404)

    # Faili ipo? Itoke moja kwa moja kutoka storage yetu.
    if not mat.file or not mat.file.storage.exists(mat.file.name):
        if not mat.original_url:
            return HttpResponse('Faili haipatikani kwenye server.', status=404)
        # AUTO-CHOTA: badala ya kumpeleka mtumiaji kwenye site ya nje,
        # pakua faili kwenye mfumo wetu mara hii hii kisha itumike.
        from ..materials_importer import download_file
        from django.core.files.base import ContentFile
        import re as _re
        data, err = download_file(mat.original_url)
        if data is None:
            return HttpResponse(
                f'Faili ya chanzo haitoshi tena ({err}). '
                f'Itachotwa upya na scheduler.', status=502)
        # download ndefu inaweza kufunga connection ya DB — funga kabla ya save
        from django.db import connection as _db_conn
        _db_conn.close()
        fname = _re.sub(r'[^A-Za-z0-9._ -]', '', mat.title)[:80] or 'material'
        if not fname.lower().endswith('.pdf'):
            fname += '.pdf'
        mat.file.save(fname, ContentFile(data), save=False)
        if not mat.file_size:
            mat.file_size = len(data)
        mat.save()

    mat.downloads += 1
    mat.save(update_fields=['downloads'])
    try:
        with open(mat.file.path, 'rb') as f:
            data = f.read()
    except OSError:
        return HttpResponse('Faili haipatikani kwenye server.', status=404)
    resp = HttpResponse(data, content_type='application/pdf')
    resp['Content-Disposition'] = f'attachment; filename="{mat.file.name.split("/")[-1]}"'
    return resp


@login_required
@require_POST
def ajax_run_maktaba_importer(request):
    """Kitufe cha admin — endesha importer sasa (sio kusubiri scheduler)."""
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'error': 'Ruhusa haitoshi.'}, status=403)
    try:
        from ..materials_importer import import_all_sources
        summary = import_all_sources(max_new_per_source=10)
        created = sum(r['created'] for r in summary['runs'])
        lines = [f"{r['source']}: {r['created']} mpya (kati ya {r['found']})" for r in summary['runs']]
        return JsonResponse({
            'success': True,
            'created': created,
            'message': '; '.join(lines) if lines else 'Hakuna vyanzo.',
        })
    except Exception as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': f'Hitilafu: {exc}'}, status=500)
