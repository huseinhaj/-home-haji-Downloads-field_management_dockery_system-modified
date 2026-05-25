import openai
import os
from dotenv import load_dotenv

load_dotenv()

# OpenAI configuration
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("⚠️ WARNING: OPENAI_API_KEY not found!")

openai.api_key = api_key

# Export client and model_name for views.py
client = openai  # This allows views.py to use client.chat.completions.create
model_name = "gpt-3.5-turbo"

print(f"✅ OpenAI configured with model: {model_name}")
print(f"🔑 API Key found: {bool(api_key)}")
