import os
from dotenv import load_dotenv
import openai

# Pakia environment variables kutoka .env file
load_dotenv()

# Pata API key kutoka environment variable
openai.api_key = os.getenv("OPENAI_API_KEY")

if not openai.api_key:
    print("ERROR: OPENAI_API_KEY haipatikani. Hakikisha umeweka .env na load_dotenv() unaitwa.")
    exit(1)

try:
    response = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "user", "content": "Hello, confirm my API key is working."}
        ],
        temperature=0
    )

    print("OpenAI API response:")
    print(response.choices[0].message.content)

except Exception as e:
    print("Kuna tatizo kuwasiliana na OpenAI API:")
    print(e)
