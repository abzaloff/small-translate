import threading
from typing import Dict, List, Tuple

import gradio as gr
from fastapi import FastAPI
from pydantic import BaseModel, Field

from modules import script_callbacks, shared

try:
    from deep_translator import GoogleTranslator
except Exception:  # pragma: no cover
    GoogleTranslator = None

try:
    from langdetect import LangDetectException, detect
except Exception:  # pragma: no cover
    LangDetectException = Exception
    detect = None


DEFAULT_ENABLED_LANGUAGES = [
    "Russian",
    "English",
    "Chinese",
    "Japanese",
    "Korean",
    "German",
    "French",
    "Spanish",
    "Italian",
    "Portuguese",
]


def _display_language_name(language_name: str) -> str:
    if language_name == "chinese (simplified)":
        return "Chinese"
    return language_name.title()


def _supported_language_codes() -> Dict[str, str]:
    if GoogleTranslator is None:
        return {
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

    try:
        supported = GoogleTranslator(source="auto", target="en").get_supported_languages(
            as_dict=True,
        )
    except Exception:  # pragma: no cover
        supported = {}

    return {
        _display_language_name(name): code
        for name, code in supported.items()
        if isinstance(name, str) and isinstance(code, str)
    }


SUPPORTED_LANGUAGE_CODES = _supported_language_codes()
LANGUAGE_CODES: Dict[str, str] = {
    "Auto Detect": "auto",
    **SUPPORTED_LANGUAGE_CODES,
}

DETECT_TO_LANGUAGE_NAME: Dict[str, str] = {
    code.lower(): name for name, code in SUPPORTED_LANGUAGE_CODES.items()
}
DETECT_TO_LANGUAGE_NAME["he"] = "Hebrew"

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


def _normalize_enabled_languages(value: object) -> List[str]:
    if not isinstance(value, (list, tuple)):
        return list(DEFAULT_ENABLED_LANGUAGES)

    enabled = []
    for language_name in value:
        if (
            isinstance(language_name, str)
            and language_name in SUPPORTED_LANGUAGE_CODES
            and language_name not in enabled
        ):
            enabled.append(language_name)

    return enabled or list(DEFAULT_ENABLED_LANGUAGES)


def _normalize_saved_enabled_languages() -> None:
    options_data = getattr(shared.opts, "data", None)
    if not isinstance(options_data, dict):
        return
    options_data["prompt_translator_enabled_languages"] = _normalize_enabled_languages(
        options_data.get("prompt_translator_enabled_languages")
    )


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
    def prompt_translator_settings_payload() -> Dict[str, object]:
        options_data = getattr(shared.opts, "data", {})
        if not isinstance(options_data, dict):
            options_data = {}
        default_source = options_data.get(
            "prompt_translator_default_source_language",
            "Auto Detect",
        )
        enabled_languages = options_data.get(
            "prompt_translator_enabled_languages",
            DEFAULT_ENABLED_LANGUAGES,
        )
        return {
            "default_source_language": _normalize_language(default_source, "Auto Detect"),
            "enabled_languages": _normalize_enabled_languages(enabled_languages),
        }

    @app.get("/prompt-translator/settings")
    def prompt_translator_settings() -> Dict[str, object]:
        return prompt_translator_settings_payload()

    @app.get("/sdapi/v1/prompt-translator/settings")
    def prompt_translator_settings_sdapi() -> Dict[str, object]:
        return prompt_translator_settings_payload()

    @app.post("/prompt-translator/translate", response_model=TranslateResponse)
    def prompt_translator_translate(payload: TranslateRequest) -> TranslateResponse:
        return _translate_text(payload.text, payload.source, payload.target)

    @app.post("/sdapi/v1/prompt-translator/translate", response_model=TranslateResponse)
    def prompt_translator_translate_sdapi(payload: TranslateRequest) -> TranslateResponse:
        return _translate_text(payload.text, payload.source, payload.target)


def _register_settings() -> None:
    section = ("prompt_translator", "Prompt Translator")
    shared.opts.add_option(
        "prompt_translator_enabled_languages",
        shared.OptionInfo(
            list(DEFAULT_ENABLED_LANGUAGES),
            "Languages shown in the translator interface",
            gr.Dropdown,
            {
                "choices": list(SUPPORTED_LANGUAGE_CODES.keys()),
                "multiselect": True,
            },
            onchange=_normalize_saved_enabled_languages,
            section=section,
        ).needs_reload_ui(),
    )
    shared.opts.add_option(
        "prompt_translator_default_source_language",
        shared.OptionInfo(
            "Auto Detect",
            "Default source language",
            gr.Dropdown,
            {"choices": list(LANGUAGE_CODES.keys())},
            section=section,
        ),
    )


script_callbacks.on_app_started(_register_routes)
script_callbacks.on_ui_settings(_register_settings)
