"""
Red-pen annotation ya karatasi — mfumo "unashika pen nyekundu" na kuandika
kwenye karatasi ya mwanafunzi kama mwalimu anavyofanya:

  ✓ (nyekundu)  jibu ni SAHIHI
  ✗ (nyekundu)  jibu ni KOSA (jibu sahihi linaonyeshwa dukazizi)
  ○ (nyekundu)  swali HALIJAJWA (kosa pia)
  Jumla         "12/30" kwa herufi kubwa nyekundu juu-kulia

Mpangilio wa bubbles ni ule ule wa scan_pdf.py / scan_grader.py (mm kwenye A4).
"""
import cv2
import numpy as np

# Sawasawa na scan_pdf.py / scan_grader.py
BUBBLE_X0_MM = 32
BUBBLE_DX_MM = 10
BUBBLE_Y0_MM = 55
BUBBLE_DY_MM = 6
BUBBLE_R_MM = 2.5

GRID_LEFT = 27 / 210
GRID_WIDTH = 40 / 210
GRID_TOP = 52 / 297
GRID_BOTTOM = 232 / 297

LETTERS = ['A', 'B', 'C', 'D']
ROWS_PER_PAGE = 30

# Rangi (BGR)
RED = (0, 0, 255)
GREEN = (0, 160, 0)      # kwa tick ndogo (hiari)
THICK = 3                # unene wa pen


def _mm_to_px(v_mm, page_max_mm, page_px):
    return int(v_mm / page_max_mm * page_px)


def annotate_sheet(image_bytes: bytes, answers: dict, answer_key: dict,
                   page_start: int = 1, total_score: int = None,
                   total_questions: int = None) -> bytes | None:
    """
    Chora alama nyekundu kwenye karatasi.

    answers:    {"1": "A", "2": None, ...} — yaliyojazwa (None=hakuna)
    answer_key: {"1": "A", ...}
    page_start: swali la kwanza kwenye ukurasa huu (mf. ukurasa 2 → 31)
    total_score/total_questions: kama ipo, andika "X/Y" juu-kulia
    """
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return None

    H, W = img.shape[:2]

    def px_x(mm):
        return int(mm / 210 * W)

    def px_y(mm):
        return int(mm / 297 * H)

    tick_len = max(6, px_y(BUBBLE_R_MM * 1.6))
    r_bubble = max(6, _mm_to_px(BUBBLE_R_MM, 210, W))

    # ------ Per-question marks ------
    for idx in range(ROWS_PER_PAGE):
        qnum = str(page_start + idx)
        if qnum not in answer_key:
            continue
        given = answers.get(qnum)
        key_ans = str(answer_key[qnum]).upper()

        # kiini cha bubble cha A (j=0); nguzo zinaonekana kutoka hapo
        cy = px_y(BUBBLE_Y0_MM + idx * BUBBLE_DY_MM)
        cx_A = px_x(BUBBLE_X0_MM)
        # tick inaandikwa kabla ya namba ya swali (upande wa kushoto)
        mx = cx_A - int(r_bubble * 2.2)
        if mx < tick_len:
            mx = tick_len + 2

        if given is None:
            # ○ duara nyekundu — swali halijajwa
            cv2.circle(img, (mx, cy), tick_len, RED, THICK)
        elif str(given).upper() == key_ans:
            # ✓ tick nyekundu
            _draw_tick(img, mx, cy, tick_len, THICK)
        else:
            # ✗ X nyekundu + dukatizi la jibu sahihi
            _draw_cross(img, mx, cy, tick_len, THICK)
            # dukatizi chini ya jibu sahihi (mwalimu anawaonesha jibu)
            j = LETTERS.index(key_ans) if key_ans in LETTERS else 0
            bx = px_x(BUBBLE_X0_MM + j * BUBBLE_DX_MM)
            by = cy + r_bubble + tick_len
            cv2.line(img, (bx - tick_len, by), (bx + tick_len, by), RED, THICK)

    # ------ Jumla juu-kulia (red pen herufi kubwa) ------
    if total_score is not None and total_questions:
        label = f'{total_score}/{total_questions}'
        # andika kwenye ukurasa wa kwanza tu; ukurasa wa mwisho una jumla kubwa
        org = (int(W * 0.55), int(H * 0.055))
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = max(0.9, W / 700)
        # box nyeupe nyuma ili isomekane juu ya picha
        (tw, th), base = cv2.getTextSize(label, font, scale, 4)
        x, y = org
        cv2.rectangle(img, (x - 10, y - th - base - 8), (x + tw + 10, y + base + 6),
                      (255, 255, 255), -1)
        cv2.putText(img, label, org, font, scale, RED, 4, cv2.LINE_AA)

    ok, buf = cv2.imencode('.png', img)
    return buf.tobytes() if ok else None


def annotate_full_sheet(image_bytes: bytes, answers: dict, answer_key: dict,
                        page_number: int, total_score: int = None,
                        total_questions: int = None,
                        n_pages: int = 1) -> bytes | None:
    """
    Annotation ya ukurasa mmoja wa karatasi ya kurasa nyingi.
    page_number (1-based) inaamua swali la kwanza: uk. 1 → 1-30, uk. 2 → 31-60...
    """
    page_start = (max(1, page_number) - 1) * ROWS_PER_PAGE + 1
    return annotate_sheet(
        image_bytes, answers, answer_key,
        page_start=page_start,
        total_score=total_score if page_number == 1 else None,
        total_questions=total_questions,
    )


def _draw_tick(img, cx, cy, size, thick):
    """Tick ✓ — mistari miwili: fupi inayopanda, ndefu inayoshuka."""
    p1 = (cx - size, cy + int(size * 0.1))
    p2 = (cx - int(size * 0.2), cy + size)
    p3 = (cx + size, cy - size)
    cv2.line(img, p1, p2, RED, thick, cv2.LINE_AA)
    cv2.line(img, p2, p3, RED, thick, cv2.LINE_AA)


def _draw_cross(img, cx, cy, size, thick):
    """X nyekundu."""
    cv2.line(img, (cx - size, cy - size), (cx + size, cy + size), RED, thick, cv2.LINE_AA)
    cv2.line(img, (cx - size, cy + size), (cx + size, cy - size), RED, thick, cv2.LINE_AA)
