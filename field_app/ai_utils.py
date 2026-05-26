import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise RuntimeError(
        "GOOGLE_API_KEY environment variable is not set. "
        "Add it to your .env file or Railway environment variables."
    )

client = genai.Client(api_key=api_key)
model_name = "gemini-2.5-flash-lite"
