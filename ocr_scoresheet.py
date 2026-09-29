"""OCR ya gridi kamili ya scoresheet ya CamScanner kwa Gemini vision.

Inatoa picha kutoka PDF, inaomba Gemini itafsiri jedwali lote (headers +
kila mstari, wakiwemo seli tupu) na kurudisha JSON.
"""
import io
import json
import re
import sys

import fitz
from google import genai
from google.genai import types
from PIL import Image

from ai_utils import client

MODEL_CANDIDATES = ["gemini-3.6-flash", "gemini-flash-latest", "gemini-2.5-flash"]


def pdf_pages_as_png_bytes(pdf_path, zoom=3.0):
    doc = fitz.open(pdf_path)
    pages = []
    for page in doc:
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        pages.append(pix.tobytes("png"))
    return pages


def main():
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else \
        "/home/haji/Downloads/CamScanner 09-11-2026 16.45 (2).pdf"

    pages = pdf_pages_as_png_bytes(pdf_path)
    print(f"Kurasa {len(pages)} zimetoholewa", file=sys.stderr)

    prompt = """Hii ni picha ya scoresheet ya alama za wanafunzi (scan ya CamScanner).

TAFSIRI JEDWALI LOTE kwa usahihi wa kina. Jibu kwa JSON TU (bila markdown fence, bila maoni):

{
  "title": "<maaneno yote yaliyoandikwa juu ya jedwali: jina la shule, mtihani, somo, class, mwaka — kama yako>",
  "columns": ["<jina la kila safu wima (column) ya somo kama liloandikwa, kuanzia kabla ya jina hadi mwisho>"],
  "rows": [
    {
      "name": "<jina la mwanafunzi kama liloandikwa kwenye mstari huo>",
      "cells": {"<column name>": <alama au null kama seli ni tupu/imekatwa X>}
    }
  ]
}

SHARTI MUHIMU:
- Soma KILA mstari na KILA seli. Seli tupu = null. USIVUNJAlini — mwanafunzi 1 = mstari 1.
- Usiingize "CamScanner" au watermark kama jina au alama.
- Kama kuna alama iliyofutwa/kukarabatiwa, tumia iliyofuta (ya mwisho).
- Alama ni namba 0-100 au null — hakuna maneno kwenye seli za alama.
- Idadi ya "rows" iwe sawa na idadi ya mistari ya wanafunzi kwenye karatasi."""

    parts = [types.Part.from_text(text=prompt)]
    for png in pages:
        img = Image.open(io.BytesIO(png)).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=92)
        parts.append(types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg"))

    resp = None
    last_err = None
    for model in MODEL_CANDIDATES:
        try:
            resp = client.models.generate_content(
                model=model,
                contents=[types.Content(role="user", parts=parts)],
                config=types.GenerateContentConfig(temperature=0),
            )
            print(f"[model ok: {model}]", file=sys.stderr)
            break
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"[model imeshindikana: {model}: {e}]", file=sys.stderr)
    if resp is None:
        raise SystemExit(f"Model zote zimeshindikana: {last_err}")

    text = resp.text.strip()
    text = re.sub(r"^```(json)?\s*|\s*```$", "", text, flags=re.S).strip()
    data = json.loads(text)
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
