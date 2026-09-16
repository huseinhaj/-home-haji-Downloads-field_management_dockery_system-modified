"""
OMR grader za Sahishi — mpangilio huu UNAOANISHWA na
`results/services/scan_pdf.py::build_answer_sheets_pdf` (bubbles kwa mm).

PDF: A4 (210 x 297 mm)
  - Swali i (i=0..29): bubble ya A (j=0) yuko x=32mm; kila nguzo +10mm
  - Safu i: y = 55 + 6*i mm kutoka juu ya ukurasa
  - Radius ya bubble: 2.5mm

Grid kwa % ya ukurasa:
  x: 32mm → 62mm  (27/210 → 67/210: nguzo 4 za 10mm, ziwe na center kwenye 32+10j)
  y: 55mm → 229mm (52/297 → 232/297, tunapunguza kidogo kwa usahihi)
"""
import cv2
import numpy as np

from .scan_qr import decode_qr

# Grid ya bubbles (kama % za A4)
GRID_TOP = 52 / 297       # juu kabisa ya grid
GRID_BOTTOM = 232 / 297   # chini kabisa ya grid
GRID_LEFT = 27 / 210      # kushoto kabisa
GRID_WIDTH = 40 / 210     # upana (nguzo 4 za 10mm; center kwa 32+10j)

ROWS = 30                 # maswali 30 kwa ukurasa
COLS = 4                  # A B C D
PASS_THRESHOLD = 0.35     # bubble inazuiwa kama "giza" zaidi ya 35%


def process_sheet(image_bytes: bytes, answer_key: dict) -> dict:
    """
    Process karatasi moja: QR + OMR + usahihishaji.
    Inarudi dict: qr, answers, score, total, needs_review, review_reason
    """
    result = {
        "qr": None,
        "answers": {},
        "score": None,
        "total": len(answer_key) if answer_key else 0,
        "needs_review": False,
        "review_reason": "",
    }

    qr_data = decode_qr(image_bytes)
    if qr_data:
        result["qr"] = qr_data
    else:
        result["needs_review"] = True
        result["review_reason"] = "QR haikusomeka"

    if answer_key:
        answers = read_answers_omr(image_bytes, rows=ROWS)
        result["answers"] = answers

        correct = 0
        for qnum, key_ans in answer_key.items():
            given = answers.get(str(qnum))
            if given is None:
                continue
            if str(given).upper() == str(key_ans).upper():
                correct += 1

        result["score"] = correct
        result["total"] = len(answer_key)

    return result


def read_answers_omr(image_bytes: bytes, rows: int = ROWS) -> dict:
    """
    Soma majibu kwa OMR. Inarudi {"1": "A", "2": None, ...}.
    None = swali halijajwa (au giza halitoshi).
    """
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return {}

    h, w = img.shape
    x0, x1 = int(w * GRID_LEFT), int(w * (GRID_LEFT + GRID_WIDTH))
    y0, y1 = int(h * GRID_TOP), int(h * GRID_BOTTOM)
    grid = img[y0:y1, x0:x1]
    if grid.size == 0:
        return {}

    gh, gw = grid.shape
    cell_h = gh / rows
    cell_w = gw / COLS

    answers = {}
    letters = ["A", "B", "C", "D"]
    for row in range(rows):
        qnum = str(row + 1)
        darkest_val, darkest_col = None, None
        for col in range(COLS):
            cx = int((col + 0.5) * cell_w)
            cy = int((row + 0.5) * cell_h)
            r = max(2, int(min(cell_h, cell_w) * 0.28))
            region = grid[max(0, cy - r):cy + r, max(0, cx - r):cx + r]
            if region.size == 0:
                continue
            mean_val = float(np.mean(region))  # 0=nyeusi, 255=nyeupe
            if darkest_val is None or mean_val < darkest_val:
                darkest_val, darkest_col = mean_val, col

        if darkest_val is not None and darkest_val < (255 * (1 - PASS_THRESHOLD)):
            answers[qnum] = letters[darkest_col]
        else:
            answers[qnum] = None

    return answers
