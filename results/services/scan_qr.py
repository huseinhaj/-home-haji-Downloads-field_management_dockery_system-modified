"""
Huduma za QR code za Sahishi:
- Kutengeneza QR ya karatasi (mtihani + mwanafunzi + ukurasa)
- Kusoma (decode) QR kutoka picha ya scan

Payload: {"e": exam_id, "s": form_student_id, "p": page_number, "sub": subject_id}
"""
import io
import json

import cv2
import numpy as np
import qrcode


def make_qr_png(exam_id: int, student_id: int, page_number: int,
                subject_id: int = 0) -> bytes:
    """Tengeneza QR code kama PNG bytes."""
    payload = json.dumps(
        {"e": exam_id, "s": student_id, "p": page_number, "sub": subject_id},
        separators=(",", ":"),
    )
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(payload)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def decode_qr(image_bytes: bytes) -> dict | None:
    """
    Soma QR code kutoka picha ya scan.
    Inarudi dict {"e","s","p","sub"} au None kama hakuna QR.
    """
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return None

    detector = cv2.QRCodeDetector()
    # Jaribu picha nzima kwanza
    data, _, _ = detector.detectAndDecode(img)
    if data:
        return _parse_payload(data)

    # Jaribu kwa Otsu threshold (scans faint/faded)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    data, _, _ = detector.detectAndDecode(thresh)
    if data:
        return _parse_payload(data)

    # Jaribu downscaled (QR kubwa kwenye picha kubwa wakati mwingine haipatikani)
    small = cv2.resize(gray, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    data, _, _ = detector.detectAndDecode(small)
    if data:
        return _parse_payload(data)

    return None


def _parse_payload(data: str) -> dict | None:
    """Parse JSON ya QR payload (inavumilia payload za zamani bila 'sub')."""
    try:
        obj = json.loads(data)
        if isinstance(obj, dict) and "e" in obj and "s" in obj and "p" in obj:
            return {
                "e": int(obj["e"]),
                "s": int(obj["s"]),
                "p": int(obj["p"]),
                "sub": int(obj.get("sub", 0)),
            }
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return None
