"""Render sample PDFs (normal + necta) for exam 59 to visually verify the
NECTA theme — light-blue page, light-yellow tables, navy text, purple
headings, double-line frames. Read-only against the dev DB.
"""
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'field_management.settings')
django.setup()

from results.models import Exam
from results.services.pdf_export_service import (
    generate_results_pdf_response,
    _build_student_result_pdf_bytes,
)

exam = Exam.objects.get(pk=59)

for style in ('normal', 'necta'):
    resp = generate_results_pdf_response(exam, style=style)
    fname = f'/tmp/necta_ref/sample_{style}.pdf'
    with open(fname, 'wb') as f:
        f.write(resp.content)
    print('wrote', fname, len(resp.content), 'bytes')

# Student slip in necta style too (first ProcessedResult of the exam)
r = exam.processedresult_set.select_related('student', 'exam').first()
if r:
    buf = _build_student_result_pdf_bytes(r, style='necta')
    with open('/tmp/necta_ref/sample_slip_necta.pdf', 'wb') as f:
        f.write(buf.read())
    print('wrote /tmp/necta_ref/sample_slip_necta.pdf')
