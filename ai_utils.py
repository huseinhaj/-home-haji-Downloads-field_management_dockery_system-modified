from google import genai
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    api_key = "AIzaSyCLfklrP_phMt3Yvm7CXuOXTDjc8isXuCQ"

client = genai.Client(api_key=api_key)
model_name = "gemini-2.0-flash"

