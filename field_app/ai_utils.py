import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()

# Gemini API configuration
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    print("⚠️ WARNING: GOOGLE_API_KEY not found in environment variables!")
    api_key = "AIzaSyCLamQ6jgOI7tcni_dbWGDFYnAslZePoRc"  # Fallback

genai.configure(api_key=api_key)
client = genai.GenerativeModel("gemini-2.0-flash")
model_name = "gemini-2.0-flash"

print(f"✅ Gemini AI configured with model: {model_name}")
print(f"🔑 API Key found: {bool(api_key)}")
