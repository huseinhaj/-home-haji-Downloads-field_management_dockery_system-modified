"""Uhakiki wa pili wa scoresheet: soma vichwa + kila namba kwa mpangilio."""
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


def main():
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else \
        "/home/haji/Downloads/CamScanner 09-11-2026 16.45 (2).pdf"
    doc = fitz.open(pdf_path)
    parts = [types.Part.from_text(text="""Nisome picha hii ya scoresheet kwa undani sana.

Jibu JSON TU:
{
 "header_text": "<MANENO yote yaliyoandikwa JUU YA jedwali — jina la shule, aina ya mtihani, darasa/class, somo, mwaka, mwalimu — kama yalivyoandikwa. Kama hakuna, weka ''>",
 "column_headers": "<majina ya safu wima za masomo, kama yalivyoandikwa, kutoka kushoto kwenda kulia, pamoja na safu ya majina wanavyoitwa>",
 "rows": [
   {"row_number": 1, "name": "...", "numbers_left_to_right": ["<kila namba au 'X' au '' kama tupu, mpangilio uleule wa safu wima>"]}
 ],
 "total_rows_on_paper": <idadi ya mistari yote ya wanafunzi kwenye karatasi>,
 "notes": "<kama kuna alama zilizofutwa, maoni, au shaka yoyote>"
}

MUHIMU: usiruke mstari wala usibadilishe mpangilio. Soma kila namba mara mbili ndani ya kichwa chako kabla kuandika.""")]
    for page in doc:
        mat = fitz.Matrix(3.5, 3.5)
        pix = page.get_pixmap(matrix=mat)
        img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        parts.append(types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg"))

    resp = None
    for model in MODEL_CANDIDATES:
        try:
            resp = client.models.generate_content(
                model=model,
                contents=[types.Content(role="user", parts=parts)],
                config=types.GenerateContentConfig(temperature=0),
            )
            break
        except Exception as e:  # noqa: BLE001
            print(f"[{model} imeshindikana: {e}]", file=sys.stderr)
    text = resp.text.strip()
    text = re.sub(r"^```(json)?\s*|\s*```$", "", text, flags=re.S).strip()
    print(json.dumps(json.loads(text), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
