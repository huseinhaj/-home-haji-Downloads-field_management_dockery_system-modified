import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")

if not api_key:
    api_key = "AIzaSyCLfklrP_phMt3Yvm7CXuOXTDjc8isXuCQ"

# Configure the API key
genai.configure(api_key=api_key)

# Create client
client = genai.GenerativeModel(model_name="gemini-2.0-flash")
model_name = "gemini-2.0-flash"

print(f"✅ Gemini AI configured with: {model_name}")
