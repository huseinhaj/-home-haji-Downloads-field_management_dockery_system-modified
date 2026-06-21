from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse

from .forms import ExamUploadForm
from .models import Exam
from .services.excel_export_service import generate_results_excel_response
from .services.pdf_export_service import generate_results_pdf_response
from .services.upload_processing_service import (
    UploadProcessingError,
    process_uploaded_results,
)

_EXAM_TYPE_CHOICES = Exam.EXAM_TYPE_CHOICES


def home(request):
    exams = Exam.objects.all().order_by('-year', 'name')
    return render(
        request,
        'results/home.html',
        {
            'exams': exams,
            'exam_count': exams.count(),
            'latest_exam': exams.first(),
        },
    )


def upload_results(request):
    exam_created = None
    no_exams = not Exam.objects.exists()

    if request.method == 'POST':
        action = request.POST.get('action', 'upload')

        if action == 'create_exam':
            name = request.POST.get('exam_name', '').strip()
            year = request.POST.get('exam_year', '2026')
            form_level = request.POST.get('exam_form', '4')
            exam_type = request.POST.get('exam_type_new', 'TERMINAL')
            if name:
                exam, created = Exam.objects.get_or_create(
                    name=name,
                    year=int(year),
                    form=int(form_level),
                    exam_type=exam_type,
                )
                exam_created = str(exam)
                no_exams = False
            form = ExamUploadForm()
            return render(request, 'results/upload.html', {
                'form': form,
                'exam_created': exam_created,
                'no_exams': no_exams,
                'exam_type_choices': _EXAM_TYPE_CHOICES,
            })

        form = ExamUploadForm(request.POST, request.FILES)
        if form.is_valid():
            exam = form.cleaned_data['exam']
            file = form.cleaned_data['file']
            try:
                process_uploaded_results(exam=exam, uploaded_file=file)
                messages.success(request, f"Matokeo yamepakiwa: {exam.name}")
                download_url = reverse('generate_results_pdf', args=[exam.id])
                return render(request, 'results/upload.html', {
                    'form': ExamUploadForm(),
                    'download_url': download_url,
                    'no_exams': False,
                    'exam_type_choices': _EXAM_TYPE_CHOICES,
                })
            except UploadProcessingError as error:
                messages.error(request, str(error))
                return redirect(request.path)
            except Exception as e:
                messages.error(request, f"Hitilafu: {str(e)}")
                return redirect(request.path)
    else:
        form = ExamUploadForm()

    return render(request, 'results/upload.html', {
        'form': form,
        'no_exams': no_exams,
        'exam_type_choices': _EXAM_TYPE_CHOICES,
    })


def filter_exams(request):
    exam_type = request.GET.get('exam_type')
    exams = Exam.objects.all()
    if exam_type:
        exams = exams.filter(exam_type=exam_type)

    options_html = render_to_string('results/exam_options.html', {'exams': exams})
    return HttpResponse(options_html)


def generate_results_pdf(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    return generate_results_pdf_response(exam)


def export_results_excel(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    return generate_results_excel_response(exam)
