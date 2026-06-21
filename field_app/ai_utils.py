import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GOOGLE_API_KEY")
client = genai.Client(api_key=api_key) if api_key else None

# Primary model has the most generous free tier (15 RPM, 1500 RPD).
# Fallbacks tried in order when 429 is hit.
model_name = "gemini-2.0-flash"
FALLBACK_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash-lite",
]
