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
    if request.method == 'POST':
        form = ExamUploadForm(request.POST, request.FILES)
        if form.is_valid():
            exam = form.cleaned_data['exam']
            file = form.cleaned_data['file']

            try:
                process_uploaded_results(exam=exam, uploaded_file=file)

                messages.success(request, f"Results uploaded and processed for exam: {exam.name}")
                download_url = reverse('generate_results_pdf', args=[exam.id])
                return render(request, 'results/upload.html', {
                    'form': ExamUploadForm(),
                    'download_url': download_url
                })
            except UploadProcessingError as error:
                messages.error(request, str(error))
                return redirect(request.path)
            except Exception as e:
                messages.error(request, f"Error processing file: {str(e)}")
                return redirect(request.path)
    else:
        form = ExamUploadForm()
    return render(request, 'results/upload.html', {'form': form})


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
