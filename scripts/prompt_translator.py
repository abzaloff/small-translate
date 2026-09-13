import json
import shutil
import subprocess
import threading
import time
from typing import Dict, List, Tuple

import gradio as gr
import requests
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

GOOGLE_TRANSLATE_URL = "https://translate.googleapis.com/translate_a/single"
GOOGLE_TRANSLATE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
GOOGLE_TRANSLATE_TIMEOUT = (5, 15)
GOOGLE_TRANSLATE_ATTEMPTS = 3
GOOGLE_TRANSLATE_CHUNK_SIZE = 3500


class GoogleTranslateRateLimitError(RuntimeError):
    """Google rejected the Python HTTP client before processing the request."""


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


def _split_translation_text(text: str) -> List[str]:
    if len(text) <= GOOGLE_TRANSLATE_CHUNK_SIZE:
        return [text]

    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= GOOGLE_TRANSLATE_CHUNK_SIZE:
            chunks.append(remaining)
            break

        split_at = remaining.rfind(" ", 0, GOOGLE_TRANSLATE_CHUNK_SIZE + 1)
        if split_at <= 0:
            split_at = GOOGLE_TRANSLATE_CHUNK_SIZE
        else:
            split_at += 1

        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:]

    return chunks


def _parse_google_translation_payload(payload: object) -> str:
    try:
        return "".join(
            part[0]
            for part in payload[0]
            if isinstance(part, list)
            and part
            and isinstance(part[0], str)
        )
    except (IndexError, TypeError):
        raise RuntimeError("Google Translate returned an invalid response") from None


def _translate_google_chunk_with_curl(
    text: str,
    source_code: str,
    target_code: str,
) -> str:
    curl = shutil.which("curl.exe") or shutil.which("curl")
    if not curl:
        raise RuntimeError("curl is not available for the Google Translate fallback")

    command = [
        curl,
        "--silent",
        "--show-error",
        "--fail",
        "--get",
        GOOGLE_TRANSLATE_URL,
        "--header",
        "User-Agent: " + GOOGLE_TRANSLATE_HEADERS["User-Agent"],
        "--header",
        "Accept-Language: " + GOOGLE_TRANSLATE_HEADERS["Accept-Language"],
    ]
    for key, value in (
        ("client", "gtx"),
        ("dt", "t"),
        ("sl", source_code),
        ("tl", target_code),
        ("q", text),
    ):
        command.extend(("--data-urlencode", f"{key}={value}"))

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="replace",
            timeout=sum(GOOGLE_TRANSLATE_TIMEOUT),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Google Translate curl fallback failed") from exc

    if completed.returncode != 0:
        message = completed.stderr.strip() or "Google Translate curl fallback failed"
        raise RuntimeError(message)

    try:
        return _parse_google_translation_payload(json.loads(completed.stdout))
    except json.JSONDecodeError as exc:
        raise RuntimeError("Google Translate returned an invalid response") from exc


def _translate_google_chunk(text: str, source_code: str, target_code: str) -> str:
    leading_whitespace = text[: len(text) - len(text.lstrip())]
    trailing_whitespace = text[len(text.rstrip()) :]
    text_to_translate = text.strip()
    if not text_to_translate:
        return text

    last_error: Exception = RuntimeError("Google Translate returned no result")

    for attempt in range(GOOGLE_TRANSLATE_ATTEMPTS):
        try:
            response = requests.get(
                GOOGLE_TRANSLATE_URL,
                params={
                    "client": "gtx",
                    "dt": "t",
                    "sl": source_code,
                    "tl": target_code,
                    "q": text_to_translate,
                },
                headers=GOOGLE_TRANSLATE_HEADERS,
                timeout=GOOGLE_TRANSLATE_TIMEOUT,
            )
            if response.status_code == 429:
                raise GoogleTranslateRateLimitError("Google Translate rate limit reached")
            response.raise_for_status()

            try:
                translated = _parse_google_translation_payload(response.json())
            except (RuntimeError, ValueError) as exc:
                raise RuntimeError("Google Translate returned an invalid response") from exc
            if not translated:
                raise RuntimeError("Google Translate returned an empty result")
            return leading_whitespace + translated + trailing_whitespace
        except (requests.RequestException, RuntimeError) as exc:
            last_error = exc
            if isinstance(exc, GoogleTranslateRateLimitError):
                break
            if attempt + 1 < GOOGLE_TRANSLATE_ATTEMPTS:
                time.sleep(0.4 * (attempt + 1))

    if isinstance(last_error, GoogleTranslateRateLimitError):
        translated = _translate_google_chunk_with_curl(
            text_to_translate,
            source_code,
            target_code,
        )
        if translated:
            return leading_whitespace + translated + trailing_whitespace

    raise last_error


def _translate_with_google(text: str, source_code: str, target_code: str) -> str:
    translated_chunks = [
        _translate_google_chunk(chunk, source_code, target_code)
        for chunk in _split_translation_text(text)
    ]
    return "".join(translated_chunks)


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
        translated = _translate_with_google(text, source_code, target_code)
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
