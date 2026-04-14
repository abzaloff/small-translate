import threading
from typing import Dict, Tuple

from fastapi import FastAPI
from pydantic import BaseModel, Field

from modules import script_callbacks

try:
    from deep_translator import GoogleTranslator
except Exception:  # pragma: no cover
    GoogleTranslator = None

try:
    from langdetect import LangDetectException, detect
except Exception:  # pragma: no cover
    LangDetectException = Exception
    detect = None


LANGUAGE_CODES: Dict[str, str] = {
    "Auto Detect": "auto",
    "Russian": "ru",
    "English": "en",
    "Chinese": "zh-CN",
    "Japanese": "ja",
    "Korean": "ko",
    "German": "de",
    "French": "fr",
    "Spanish": "es",
    "Italian": "it",
    "Portuguese": "pt",
}

DETECT_TO_LANGUAGE_NAME: Dict[str, str] = {
    "ru": "Russian",
    "en": "English",
    "zh-cn": "Chinese",
    "zh-tw": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
}

_translation_cache: Dict[Tuple[str, str, str], str] = {}
_cache_lock = threading.Lock()


class TranslateRequest(BaseModel):
    text: str = Field(default="")
    source: str = Field(default="Auto Detect")
    target: str = Field(default="English")


class TranslateResponse(BaseModel):
    translated_text: str
    used_cache: bool = False
    ok: bool = True
    error: str = ""
    detected_source: str = ""


def _normalize_language(language_name: str, fallback: str) -> str:
    if language_name == "auto":
        return "Auto Detect"
    if language_name in LANGUAGE_CODES:
        return language_name
    return fallback


def _translate_text(text: str, source_name: str, target_name: str) -> TranslateResponse:
    source_name = _normalize_language(source_name, "Auto Detect")
    target_name = _normalize_language(target_name, "English")

    if not text or not text.strip():
        return TranslateResponse(translated_text=text, used_cache=False, ok=True)

    if source_name != "Auto Detect" and source_name == target_name:
        return TranslateResponse(translated_text=text, used_cache=False, ok=True)

    source_code = LANGUAGE_CODES[source_name]
    target_code = LANGUAGE_CODES[target_name]
    detected_source = ""
    if source_code == "auto" and detect is not None:
        try:
            detected_code = detect(text).lower()
            detected_source = DETECT_TO_LANGUAGE_NAME.get(detected_code, "")
        except LangDetectException:
            detected_source = ""

    cache_key = (text, source_code, target_code)
    with _cache_lock:
        cached = _translation_cache.get(cache_key)
    if cached is not None:
        return TranslateResponse(
            translated_text=cached,
            used_cache=True,
            ok=True,
            detected_source=detected_source,
        )

    if GoogleTranslator is None:
        return TranslateResponse(
            translated_text=text,
            used_cache=False,
            ok=False,
            error="deep-translator is not available",
        )

    try:
        translated = GoogleTranslator(source=source_code, target=target_code).translate(text)
        if translated is None:
            translated = text

        with _cache_lock:
            _translation_cache[cache_key] = translated

        return TranslateResponse(
            translated_text=translated,
            used_cache=False,
            ok=True,
            detected_source=detected_source,
        )
    except Exception as exc:  # pragma: no cover
        return TranslateResponse(
            translated_text=text,
            used_cache=False,
            ok=False,
            error=str(exc),
        )


def _register_routes(_: object, app: FastAPI) -> None:
    @app.post("/prompt-translator/translate", response_model=TranslateResponse)
    def prompt_translator_translate(payload: TranslateRequest) -> TranslateResponse:
        return _translate_text(payload.text, payload.source, payload.target)

    @app.post("/sdapi/v1/prompt-translator/translate", response_model=TranslateResponse)
    def prompt_translator_translate_sdapi(payload: TranslateRequest) -> TranslateResponse:
        return _translate_text(payload.text, payload.source, payload.target)


script_callbacks.on_app_started(_register_routes)
