"""LLM-based text summarization service using Groq API."""
import os

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

from config import get_settings

settings = get_settings()

# Max characters to send to LLM per request (Groq context limit ~128k tokens, be conservative)
MAX_INPUT_CHARS = 100_000


def _get_client() -> "Groq":
    if not GROQ_AVAILABLE:
        raise RuntimeError("groq package not installed. Run: pip install groq")
    api_key = settings.groq_api_key or os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY not set. Get a free API key at https://console.groq.com and set GROQ_API_KEY in .env"
        )
    return Groq(api_key=api_key)


def summarize_text(text: str) -> str:
    """
    Summarize the given text using an LLM (Groq / Llama).
    """
    if not text or not text.strip():
        return ""

    # Truncate if very long
    if len(text) > MAX_INPUT_CHARS:
        text = text[:MAX_INPUT_CHARS] + "\n\n[Text truncated...]"

    client = _get_client()

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant that creates clear, concise summaries. "
                    "Summarize the following text into one single paragraph, capturing the main points and key information. "
                    "Be thorough but concise."
                ),
            },
            {"role": "user", "content": text},
        ],
        temperature=0.3,
        max_tokens=1024,
    )

    if not response.choices:
        raise RuntimeError("No response from LLM. Please try again.")

    content = response.choices[0].message.content
    return (content or "").strip()
