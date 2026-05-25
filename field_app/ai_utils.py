import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    print("⚠️ GOOGLE_API_KEY not found!")
    api_key = "YOUR_BACKUP_KEY"

genai.configure(api_key=api_key)

# Tumia Gemini 2.5 Flash-Lite - quota kubwa na nafuu
client = genai.GenerativeModel("gemini-2.5-flash-lite")
model_name = "gemini-2.5-flash-lite"

print(f"✅ Gemini AI configured with: {model_name}")
print(f"🔑 API Key found: {bool(api_key)}")
