import os
from openai import OpenAI
from dotenv import load_dotenv

# Loads OPENROUTER_API_KEY from the .env file (which is git-ignored).
load_dotenv()

# OpenRouter is OpenAI-compatible: same SDK, just a different base_url.
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
)

completion = client.chat.completions.create(
    model="qwen/qwen3.6-35b-a3b",
    messages=[
        {"role": "system", "content": "Tu es un assistant utile."},
        {"role": "user", "content": "est ce que la paroxétine est indiquée chez la personne agée."},
    ],
    max_tokens=512,
    extra_body={"reasoning": {"enabled": False}},
)

print(completion.choices[0].message.content)
