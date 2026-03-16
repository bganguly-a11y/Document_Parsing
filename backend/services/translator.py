"""Translation service using deep-translator."""
from deep_translator import GoogleTranslator

_DEFAULT_SUPPORTED_LANGUAGES: dict[str, str] = {
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

def _build_supported_languages() -> dict[str, str]:
    """
    Build a (code -> display name) map from deep-translator's built-in list.

    deep-translator exposes languages as a dict of (name -> code). We invert it
    for the API/UI and title-case the display name.
    """
    try:
        t = GoogleTranslator(source="auto", target="en")
        name_to_code = t.get_supported_languages(as_dict=True)
        code_to_name = {code: name.title() for name, code in name_to_code.items()}

        # Ensure a few common codes are present with friendly names.
        code_to_name.setdefault("zh-CN", "Chinese (Simplified)")
        code_to_name.setdefault("zh-TW", "Chinese (Traditional)")
        return dict(sorted(code_to_name.items(), key=lambda kv: kv[1].lower()))
    except Exception:
        # If deep-translator changes or fails, fall back to a small curated set.
        return dict(sorted(_DEFAULT_SUPPORTED_LANGUAGES.items(), key=lambda kv: kv[1].lower()))


# Supported target languages (code -> display name).
# Includes many more languages (including Indian languages like Bengali, Kannada, Telugu, etc.).
SUPPORTED_LANGUAGES = _build_supported_languages()


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
