import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    api_key = "AIzaSyAkNpK-mUEOBCiva_QpDe-62sdyWqlzP8c"

genai.configure(api_key=api_key)

# Tumia Flash-Lite - quota kubwa
client = genai.GenerativeModel("gemini-2.5-flash-lite")
model_name = "gemini-2.5-flash-lite"

print(f"✅ Gemini AI configured with: {model_name}")
