"""
PDF generator ya karatasi za majibu za Sahishi.

MUHIMU: Mpangilio wa bubbles hapa unaoanishwa na scan_grader.py:
  - Swali i (i=0..29): bubble A x=32mm, kila nguzo +10mm
  - Safu i: y = 55 + 6*i mm kutoka juu
  - Bubble radius: 2.5mm
"""
import io

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .scan_qr import make_qr_png

# Constants sawa na scan_grader.py
BUBBLE_X0_MM = 32        # bubble A ya swali la kwanza
BUBBLE_DX_MM = 10        # pengo kati ya nguzo (A→B→C→D)
BUBBLE_Y0_MM = 55        # safu ya kwanza (kutoka juu)
BUBBLE_DY_MM = 6         # pengo kati ya safu
BUBBLE_R_MM = 2.5        # radius ya bubble
N_QUESTIONS = 30         # maswali 30 kwa ukurasa
LETTERS = ["A", "B", "C", "D"]


def build_answer_sheets_pdf(exam, subject, students, pages_per_student=1) -> bytes:
    """
    Tengeneza PDF ya karatasi za majibu za wanafunzi wote wa mtihani huu.
    Kila ukurasa: QR (mtihani+somu+mwanafunzi+uk.), header, na bubbles 30x4.
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    for fs in students:
        student_name = fs.full_name
        if callable(student_name):
            student_name = student_name()
        for page in range(1, pages_per_student + 1):
            # Header
            c.setFont("Helvetica-Bold", 13)
            c.drawString(20 * mm, height - 18 * mm, exam.name[:60])
            c.setFont("Helvetica", 9)
            c.drawString(20 * mm, height - 24 * mm,
                         f"{exam.get_exam_type_display()} | Form {exam.form}"
                         f"{' ' + exam.stream if exam.stream else ''} | {exam.year}")
            c.setFont("Helvetica-Bold", 10)
            c.drawString(20 * mm, height - 31 * mm, f"Somo: {subject.name}")

            # Mwanafunzi
            c.setFont("Helvetica-Bold", 10)
            c.drawString(20 * mm, height - 40 * mm, f"Mwanafunzi: {student_name}")
            if fs.admission_no:
                c.setFont("Helvetica", 9)
                c.drawString(20 * mm, height - 45 * mm,
                             f"Namba: {fs.admission_no}")
            c.setFont("Helvetica", 9)
            c.drawString(20 * mm, height - 50 * mm,
                         f"Karatasi: {page}/{pages_per_student}")

            # QR code (juu-kulia)
            qr_bytes = make_qr_png(exam.pk, fs.pk, page, subject.pk)
            c.drawImage(ImageReader(io.BytesIO(qr_bytes)),
                        width - 40 * mm, height - 42 * mm,
                        22 * mm, 22 * mm)

            # Maelekezo
            c.setFont("Helvetica-Oblique", 8)
            c.drawString(20 * mm, height - 51 * mm - 2,
                         "Jaza jibu kwa ku-fanya giza ndani ya duara (A B C D) kwa pen ya blu")

            # Bubbles grid
            c.setFont("Helvetica", 9)
            for i in range(N_QUESTIONS):
                y = (BUBBLE_Y0_MM + i * BUBBLE_DY_MM) * mm
                y_from_top = height - y  # reportlab: y kutoka chini
                if y_from_top < 20 * mm:
                    break
                # Namba ya swali
                c.setFont("Helvetica", 8)
                c.drawString(20 * mm, y_from_top, f"{i + 1}.")
                # Bubbles
                for j, letter in enumerate(LETTERS):
                    bx = (BUBBLE_X0_MM + j * BUBBLE_DX_MM) * mm
                    c.setLineWidth(0.8)
                    c.circle(bx, y_from_top + BUBBLE_R_MM, BUBBLE_R_MM * mm,
                             stroke=1, fill=0)
                    c.setFont("Helvetica", 6)
                    c.drawString(bx - 1.2 * mm, y_from_top - 1.8 * mm, letter)

            c.showPage()

    c.save()
    return buf.getvalue()
