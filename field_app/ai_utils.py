import openai
import os
from dotenv import load_dotenv

load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")
model_name = "gpt-3.5-turbo"

print(f"✅ OpenAI configured with model: {model_name}")
print(f"🔑 API Key found: {bool(openai.api_key)}")
