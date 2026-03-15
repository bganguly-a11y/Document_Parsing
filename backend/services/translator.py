"""Translation service using deep-translator."""
from deep_translator import GoogleTranslator

# Supported target languages (code -> display name)
SUPPORTED_LANGUAGES = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "hi": "Hindi",
    "ja": "Japanese",
    "zh-CN": "Chinese (Simplified)",
    "ko": "Korean",
    "ar": "Arabic",
    "ru": "Russian",
}


def translate_text(text: str, target_lang: str, source_lang: str | None = "auto") -> str:
    """
    Translate text to target language using Google Translate.
    deep-translator has ~2000 char limit per request; we chunk if needed.
    """
    if not text or not text.strip():
        return text
    
    target_lang = target_lang or "en"
    translator = GoogleTranslator(source=source_lang or "auto", target=target_lang)
    
    # Chunk text to avoid API limits (~2000 chars)
    chunk_size = 1800
    chunks = [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]
    translated = [translator.translate(chunk) for chunk in chunks]
    
    return "".join(translated) if translated else text
