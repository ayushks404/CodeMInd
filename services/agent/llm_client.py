"""
llm_client.py — Groq LLM client replacing OpenRouter

Why Groq:
- Free tier available at groq.com
- Extremely fast inference (runs on custom LPU hardware)
- Uses Llama 3.3 70B — much better than GPT-3.5-turbo
- Simple REST API, same structure as OpenAI

Setup: get your free key at https://console.groq.com
Add to .env:  GROQ_API_KEY=gsk_...
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"
MODEL        = "llama-3.3-70b-versatile"   # best free Groq model for code tasks


def generate(prompt: str) -> str:
    """
    Send a prompt to Groq and return the response text.

    Drop-in replacement for the old OpenRouter generate() function.
    Same signature — app.py and rag_engine.py need no changes.

    Args:
        prompt: Full prompt string (system message prepended internally)

    Returns:
        LLM response as a string (markdown formatted)
    """
    if not GROQ_API_KEY:
        raise ValueError(
            "GROQ_API_KEY not set. "
            "Get your free key at https://console.groq.com and add it to .env"
        )

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type":  "application/json",
    }

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role":    "system",
                "content": (
                    "You are a senior software engineer and codebase analyst. "
                    "You answer questions about codebases accurately and concisely. "
                    "You always reference specific files and functions. "
                    "You format all responses in clean markdown with code blocks."
                ),
            },
            {
                "role":    "user",
                "content": prompt,
            },
        ],
        "temperature": 0.3,    # low temp = more factual, less hallucination
        "max_tokens":  1024,   # enough for detailed code explanations
    }

    response = requests.post(GROQ_URL, headers=headers, json=payload, timeout=30)

    if response.status_code != 200:
        raise Exception(f"Groq API error {response.status_code}: {response.text}")

    return response.json()["choices"][0]["message"]["content"]
