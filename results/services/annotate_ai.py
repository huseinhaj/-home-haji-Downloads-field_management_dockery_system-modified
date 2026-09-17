"""
Annotation ya karatasi iliyosahihishwa na AI (ai_grader.py).

Badala ya bubbles (scan_annotate.py), hii inachora kwenye karatasi HALISI:
  - kwenye kila swali: mduara nyekundu + "alama/max" (mf. "2/3")
  - ✓ (kijani) kwa alama kamili, ✗ (nyekundu) kwa alama zilizopungua
  - juu kulia: sanduku la JUMLA (mf. "17/30")

bbox za maswali zinakuja kutoka AI kama % za ukurasa (x, y: 0-100).
"""
from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFont

RED = (215, 30, 30)
GREEN = (0, 130, 60)
DARK = (30, 30, 30)


def _font(size: int):
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def annotate_ai_sheet(image_bytes: bytes, grade: dict) -> bytes | None:
    """Chora alama za AI kwenye picha ya karatasi. Inarudi PNG bytes au None."""
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        return None

    w, h = img.size
    draw = ImageDraw.Draw(img)
    # Vipimo vya fonti vinafuata upana wa picha (scan 150-300dpi)
    base = max(14, w // 55)
    f_mark = _font(base)
    f_total = _font(int(base * 1.5))

    questions = grade.get("questions") or []
    for q in questions:
        bbox = q.get("bbox") or []
        # AI inaweza kurudisha [x, y] au [x1, y1, x2, y2] — tumia kona ya
        # juu-kushoto ya jibu kwa zote mbili.
        if len(bbox) not in (2, 4):
            continue
        try:
            x = min(95.0, max(2.0, float(bbox[0]))) / 100.0 * w
            y = min(95.0, max(2.0, float(bbox[1]))) / 100.0 * h
        except (TypeError, ValueError):
            continue

        full = bool(q.get("correct"))
        color = GREEN if full else RED
        r = int(base * 1.6)

        # Mduara kwenye mwanzo wa jibu la mwanafunzi
        draw.ellipse(
            [x - r, y - r, x + r, y + r],
            outline=color, width=max(3, int(base / 5)),
        )
        # Alama karibu na mduara: "2/3" au "5/5"
        label = f"{q.get('score', 0)}/{q.get('max', '?')}"
        lx, ly = x + r + int(base * 0.3), y - r
        # Background nyeupe kidogo ili label isomekane
        tb = draw.textbbox((lx, ly), label, font=f_mark)
        draw.rectangle([tb[0] - 3, tb[1] - 2, tb[2] + 3, tb[3] + 2], fill=(255, 255, 255))
        draw.text((lx, ly), label, fill=color, font=f_mark)

        # Note fupi (kama ipo) chini ya alama
        note = (q.get("note") or "").strip()
        if note and not full:
            small = _font(int(base * 0.75))
            t2 = draw.textbbox((lx, tb[3] + 4), note, font=small)
            t2 = (t2[0], t2[1], min(t2[2], w - 8), t2[3])
            draw.rectangle([t2[0] - 3, t2[1] - 2, t2[2] + 3, t2[3] + 2], fill=(255, 255, 255))
            draw.text((t2[0], t2[1]), note, fill=DARK, font=small)

    # Sanduku la JUMLA juu kulia
    total = grade.get("total")
    max_total = grade.get("max_total")
    if total is not None:
        tlabel = f"{total}/{max_total if max_total is not None else '?'}"
        tb = draw.textbbox((0, 0), tlabel, font=f_total)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        pad = int(base * 0.6)
        x1, y1 = w - tw - pad * 3, int(h * 0.03)
        x2, y2 = x1 + tw + pad * 2, y1 + th + pad
        draw.rectangle([x1, y1, x2, y2], outline=RED, width=max(4, int(base / 4)))
        draw.rectangle([x1 + 4, y1 + 4, x2 - 4, y2 - 4], fill=(255, 255, 255))
        draw.text((x1 + pad, y1 + pad // 2), tlabel, fill=RED, font=f_total)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
