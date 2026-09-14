import gc
import json
import os
import shutil
import subprocess
import threading
import time
from typing import Dict, List, Tuple

import gradio as gr
import requests
from fastapi import FastAPI
from pydantic import BaseModel, Field

from modules import paths, script_callbacks, shared

try:
    from deep_translator import GoogleTranslator
except Exception:  # pragma: no cover
    GoogleTranslator = None

try:
    from langdetect import LangDetectException, detect
except Exception:  # pragma: no cover
    LangDetectException = Exception
    detect = None

try:
    import torch
    from transformers import AutoTokenizer
except Exception:  # pragma: no cover
    torch = None
    AutoTokenizer = None

try:
    import ctranslate2
except Exception:  # pragma: no cover
    ctranslate2 = None

try:
    from huggingface_hub import snapshot_download
except Exception:  # pragma: no cover
    snapshot_download = None


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

NLLB_LANGUAGE_CODES = dict(
    line.split("|")
    for line in """
Acehnese (Arabic script)|ace_Arab
Acehnese (Latin script)|ace_Latn
Mesopotamian Arabic|acm_Arab
Ta’izzi-Adeni Arabic|acq_Arab
Tunisian Arabic|aeb_Arab
Afrikaans|afr_Latn
South Levantine Arabic|ajp_Arab
Akan|aka_Latn
Amharic|amh_Ethi
North Levantine Arabic|apc_Arab
Modern Standard Arabic|arb_Arab
Modern Standard Arabic (Romanized)|arb_Latn
Najdi Arabic|ars_Arab
Moroccan Arabic|ary_Arab
Egyptian Arabic|arz_Arab
Assamese|asm_Beng
Asturian|ast_Latn
Awadhi|awa_Deva
Central Aymara|ayr_Latn
South Azerbaijani|azb_Arab
North Azerbaijani|azj_Latn
Bashkir|bak_Cyrl
Bambara|bam_Latn
Balinese|ban_Latn
Belarusian|bel_Cyrl
Bemba|bem_Latn
Bengali|ben_Beng
Bhojpuri|bho_Deva
Banjar (Arabic script)|bjn_Arab
Banjar (Latin script)|bjn_Latn
Standard Tibetan|bod_Tibt
Bosnian|bos_Latn
Buginese|bug_Latn
Bulgarian|bul_Cyrl
Catalan|cat_Latn
Cebuano|ceb_Latn
Czech|ces_Latn
Chokwe|cjk_Latn
Central Kurdish|ckb_Arab
Crimean Tatar|crh_Latn
Welsh|cym_Latn
Danish|dan_Latn
German|deu_Latn
Southwestern Dinka|dik_Latn
Dyula|dyu_Latn
Dzongkha|dzo_Tibt
Greek|ell_Grek
English|eng_Latn
Esperanto|epo_Latn
Estonian|est_Latn
Basque|eus_Latn
Ewe|ewe_Latn
Faroese|fao_Latn
Fijian|fij_Latn
Finnish|fin_Latn
Fon|fon_Latn
French|fra_Latn
Friulian|fur_Latn
Nigerian Fulfulde|fuv_Latn
Scottish Gaelic|gla_Latn
Irish|gle_Latn
Galician|glg_Latn
Guarani|grn_Latn
Gujarati|guj_Gujr
Haitian Creole|hat_Latn
Hausa|hau_Latn
Hebrew|heb_Hebr
Hindi|hin_Deva
Chhattisgarhi|hne_Deva
Croatian|hrv_Latn
Hungarian|hun_Latn
Armenian|hye_Armn
Igbo|ibo_Latn
Ilocano|ilo_Latn
Indonesian|ind_Latn
Icelandic|isl_Latn
Italian|ita_Latn
Javanese|jav_Latn
Japanese|jpn_Jpan
Kabyle|kab_Latn
Jingpho|kac_Latn
Kamba|kam_Latn
Kannada|kan_Knda
Kashmiri (Arabic script)|kas_Arab
Kashmiri (Devanagari script)|kas_Deva
Georgian|kat_Geor
Central Kanuri (Arabic script)|knc_Arab
Central Kanuri (Latin script)|knc_Latn
Kazakh|kaz_Cyrl
Kabiyè|kbp_Latn
Kabuverdianu|kea_Latn
Khmer|khm_Khmr
Kikuyu|kik_Latn
Kinyarwanda|kin_Latn
Kyrgyz|kir_Cyrl
Kimbundu|kmb_Latn
Northern Kurdish|kmr_Latn
Kikongo|kon_Latn
Korean|kor_Hang
Lao|lao_Laoo
Ligurian|lij_Latn
Limburgish|lim_Latn
Lingala|lin_Latn
Lithuanian|lit_Latn
Lombard|lmo_Latn
Latgalian|ltg_Latn
Luxembourgish|ltz_Latn
Luba-Kasai|lua_Latn
Ganda|lug_Latn
Luo|luo_Latn
Mizo|lus_Latn
Standard Latvian|lvs_Latn
Magahi|mag_Deva
Maithili|mai_Deva
Malayalam|mal_Mlym
Marathi|mar_Deva
Minangkabau (Arabic script)|min_Arab
Minangkabau (Latin script)|min_Latn
Macedonian|mkd_Cyrl
Plateau Malagasy|plt_Latn
Maltese|mlt_Latn
Meitei (Bengali script)|mni_Beng
Halh Mongolian|khk_Cyrl
Mossi|mos_Latn
Maori|mri_Latn
Burmese|mya_Mymr
Dutch|nld_Latn
Norwegian Nynorsk|nno_Latn
Norwegian Bokmål|nob_Latn
Nepali|npi_Deva
Northern Sotho|nso_Latn
Nuer|nus_Latn
Nyanja|nya_Latn
Occitan|oci_Latn
West Central Oromo|gaz_Latn
Odia|ory_Orya
Pangasinan|pag_Latn
Eastern Panjabi|pan_Guru
Papiamento|pap_Latn
Western Persian|pes_Arab
Polish|pol_Latn
Portuguese|por_Latn
Dari|prs_Arab
Southern Pashto|pbt_Arab
Ayacucho Quechua|quy_Latn
Romanian|ron_Latn
Rundi|run_Latn
Russian|rus_Cyrl
Sango|sag_Latn
Sanskrit|san_Deva
Santali|sat_Olck
Sicilian|scn_Latn
Shan|shn_Mymr
Sinhala|sin_Sinh
Slovak|slk_Latn
Slovenian|slv_Latn
Samoan|smo_Latn
Shona|sna_Latn
Sindhi|snd_Arab
Somali|som_Latn
Southern Sotho|sot_Latn
Spanish|spa_Latn
Tosk Albanian|als_Latn
Sardinian|srd_Latn
Serbian|srp_Cyrl
Swati|ssw_Latn
Sundanese|sun_Latn
Swedish|swe_Latn
Swahili|swh_Latn
Silesian|szl_Latn
Tamil|tam_Taml
Tatar|tat_Cyrl
Telugu|tel_Telu
Tajik|tgk_Cyrl
Tagalog|tgl_Latn
Thai|tha_Thai
Tigrinya|tir_Ethi
Tamasheq (Latin script)|taq_Latn
Tamasheq (Tifinagh script)|taq_Tfng
Tok Pisin|tpi_Latn
Tswana|tsn_Latn
Tsonga|tso_Latn
Turkmen|tuk_Latn
Tumbuka|tum_Latn
Turkish|tur_Latn
Twi|twi_Latn
Central Atlas Tamazight|tzm_Tfng
Uyghur|uig_Arab
Ukrainian|ukr_Cyrl
Umbundu|umb_Latn
Urdu|urd_Arab
Northern Uzbek|uzn_Latn
Venetian|vec_Latn
Vietnamese|vie_Latn
Waray|war_Latn
Wolof|wol_Latn
Xhosa|xho_Latn
Eastern Yiddish|ydd_Hebr
Yoruba|yor_Latn
Yue Chinese|yue_Hant
Chinese (Traditional)|zho_Hant
Standard Malay|zsm_Latn
Zulu|zul_Latn
""".strip().splitlines()
)
NLLB_LANGUAGE_CODES.update(
    {
        "Arabic": "arb_Arab",
        "Aymara": "ayr_Latn",
        "Chinese": "zho_Hans",
        "Kurdish": "kmr_Latn",
        "Latvian": "lvs_Latn",
        "Malay": "zsm_Latn",
        "Mongolian": "khk_Cyrl",
        "Norwegian": "nob_Latn",
        "Pashto": "pbt_Arab",
        "Persian": "pes_Arab",
        "Punjabi": "pan_Guru",
        "Quechua": "quy_Latn",
        "Tibetan": "bod_Tibt",
        "Uzbek": "uzn_Latn",
        "Yiddish": "ydd_Hebr",
    }
)
NLLB_PROVIDER = "NLLB-200 (local)"
GOOGLE_PROVIDER = "Google (online)"
NLLB_DEFAULT_MODEL_PATH = os.path.join(
    paths.models_path,
    "prompt-translator",
    "nllb-200-distilled-600M-ct2-int8",
)
NLLB_CHUNK_SIZE = 1200
NLLB_MODEL_REPOSITORY = "JustFrederik/nllb-200-distilled-600M-ct2-int8"
NLLB_DOWNLOAD_SIZE_BYTES = 650_000_000
NLLB_REQUIRED_FILES = (
    "config.json",
    "model.bin",
    "sentencepiece.bpe.model",
    "shared_vocabulary.txt",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
)


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
INTERFACE_LANGUAGE_NAMES = set(SUPPORTED_LANGUAGE_CODES) | set(NLLB_LANGUAGE_CODES)

DETECT_TO_LANGUAGE_NAME: Dict[str, str] = {
    code.lower(): name for name, code in SUPPORTED_LANGUAGE_CODES.items()
}
DETECT_TO_LANGUAGE_NAME["he"] = "Hebrew"

_translation_cache: Dict[Tuple[str, str, str, str], str] = {}
_cache_lock = threading.Lock()
_nllb_lock = threading.Lock()
_nllb_model = None
_nllb_tokenizer = None
_nllb_model_path = ""
_nllb_device = ""
_nllb_download_lock = threading.Lock()
_nllb_download_thread = None
_nllb_download_state = {
    "model_path": "",
    "state": "idle",
    "error": "",
}

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


class NllbDownloadRequest(BaseModel):
    model_path: str = Field(default="")


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
            and language_name in INTERFACE_LANGUAGE_NAMES
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


def _split_translation_text(text: str, chunk_size: int) -> List[str]:
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= chunk_size:
            chunks.append(remaining)
            break

        split_at = remaining.rfind(" ", 0, chunk_size + 1)
        if split_at <= 0:
            split_at = chunk_size
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
        for chunk in _split_translation_text(text, GOOGLE_TRANSLATE_CHUNK_SIZE)
    ]
    return "".join(translated_chunks)


def _get_translation_provider() -> str:
    options_data = getattr(shared.opts, "data", {})
    if not isinstance(options_data, dict):
        options_data = {}
    provider = options_data.get(
        "prompt_translator_provider",
        GOOGLE_PROVIDER,
    )
    return provider if provider in (GOOGLE_PROVIDER, NLLB_PROVIDER) else GOOGLE_PROVIDER


def _get_nllb_model_path() -> str:
    options_data = getattr(shared.opts, "data", {})
    if not isinstance(options_data, dict):
        options_data = {}
    configured_path = options_data.get(
        "prompt_translator_nllb_model_path",
        NLLB_DEFAULT_MODEL_PATH,
    )
    if not isinstance(configured_path, str) or not configured_path.strip():
        return NLLB_DEFAULT_MODEL_PATH
    return os.path.abspath(configured_path.strip())


def _get_nllb_execution_device() -> str:
    options_data = getattr(shared.opts, "data", {})
    if not isinstance(options_data, dict):
        options_data = {}
    selected_device = options_data.get("prompt_translator_nllb_device", "GPU")
    if selected_device == "CPU":
        return "cpu"
    if torch is None or not torch.cuda.is_available():
        raise RuntimeError(
            "NLLB GPU mode is selected, but CUDA is unavailable. "
            "Select CPU under Settings > Prompt Translator."
        )
    return "cuda"


def _normalize_nllb_model_path(model_path: object) -> str:
    if not isinstance(model_path, str) or not model_path.strip():
        return _get_nllb_model_path()
    return os.path.abspath(model_path.strip())


def _nllb_model_is_ready(model_path: str) -> bool:
    return all(
        os.path.isfile(os.path.join(model_path, filename))
        for filename in NLLB_REQUIRED_FILES
    )


def _nllb_downloaded_bytes(model_path: str) -> int:
    if not os.path.isdir(model_path):
        return 0

    total = 0
    for root, _, filenames in os.walk(model_path):
        for filename in filenames:
            try:
                total += os.path.getsize(os.path.join(root, filename))
            except OSError:
                pass
    return total


def _nllb_status(model_path: object = "") -> Dict[str, object]:
    normalized_path = _normalize_nllb_model_path(model_path)
    with _nllb_download_lock:
        state = dict(_nllb_download_state)
        download_in_progress = (
            state["state"] == "downloading"
            and state["model_path"] == normalized_path
        )

    downloaded_bytes = _nllb_downloaded_bytes(normalized_path)
    ready = _nllb_model_is_ready(normalized_path)
    loaded = _nllb_model is not None and _nllb_model_path == normalized_path
    loaded_any = _nllb_model is not None
    return {
        "model_path": normalized_path,
        "ready": ready,
        "loaded": loaded,
        "loaded_any": loaded_any,
        "loaded_model_path": _nllb_model_path if loaded_any else "",
        "execution_device": _nllb_device if loaded_any else "",
        "downloading": download_in_progress,
        "download_state": (
            state["state"]
            if state["model_path"] == normalized_path and state["state"] == "error"
            else "downloading"
            if download_in_progress
            else "ready"
            if ready
            else "idle"
        ),
        "downloaded_bytes": downloaded_bytes,
        "total_bytes": NLLB_DOWNLOAD_SIZE_BYTES,
        "progress_percent": min(
            100,
            round(downloaded_bytes * 100 / NLLB_DOWNLOAD_SIZE_BYTES, 1),
        ),
        "error": state["error"] if state["model_path"] == normalized_path else "",
    }


def _download_nllb_model(model_path: str) -> None:
    global _nllb_download_thread, _nllb_download_state

    try:
        if snapshot_download is None:
            raise RuntimeError(
                "NLLB download requires huggingface_hub. Restart Forge after "
                "installing the extension dependencies."
            )

        os.makedirs(model_path, exist_ok=True)
        snapshot_download(
            repo_id=NLLB_MODEL_REPOSITORY,
            local_dir=model_path,
            allow_patterns=list(NLLB_REQUIRED_FILES),
        )
        if not _nllb_model_is_ready(model_path):
            raise RuntimeError("The NLLB download completed but required files are missing.")

        with _nllb_download_lock:
            _nllb_download_state = {
                "model_path": model_path,
                "state": "ready",
                "error": "",
            }
    except Exception as exc:  # pragma: no cover - depends on network/filesystem
        with _nllb_download_lock:
            _nllb_download_state = {
                "model_path": model_path,
                "state": "error",
                "error": str(exc),
            }
    finally:
        with _nllb_download_lock:
            _nllb_download_thread = None


def _start_nllb_download(model_path: object = "") -> Dict[str, object]:
    global _nllb_download_state, _nllb_download_thread

    normalized_path = _normalize_nllb_model_path(model_path)
    with _nllb_download_lock:
        if _nllb_download_thread is not None and _nllb_download_thread.is_alive():
            already_downloading = True
        else:
            already_downloading = False

        if not already_downloading and _nllb_model_is_ready(normalized_path):
            model_is_ready = True
        else:
            model_is_ready = False

        if not already_downloading and not model_is_ready:
            _nllb_download_state = {
                "model_path": normalized_path,
                "state": "downloading",
                "error": "",
            }
            _nllb_download_thread = threading.Thread(
                target=_download_nllb_model,
                args=(normalized_path,),
                daemon=True,
                name="prompt-translator-nllb-download",
            )
            _nllb_download_thread.start()

    if already_downloading:
        return {
            "ok": False,
            "error": "An NLLB download is already running.",
            **_nllb_status(normalized_path),
        }
    if model_is_ready:
        return {"ok": True, **_nllb_status(normalized_path)}

    return {"ok": True, **_nllb_status(normalized_path)}


def _unload_nllb_model() -> Dict[str, object]:
    global _nllb_device, _nllb_model, _nllb_model_path, _nllb_tokenizer

    with _nllb_lock:
        model_path = _nllb_model_path
        model = _nllb_model
        tokenizer = _nllb_tokenizer
        _nllb_model = None
        _nllb_tokenizer = None
        _nllb_model_path = ""
        _nllb_device = ""

    if model is not None:
        try:
            model.unload_model()
        except Exception:
            pass
    del model
    del tokenizer
    gc.collect()
    if torch is not None and torch.cuda.is_available():
        torch.cuda.empty_cache()

    with _cache_lock:
        nllb_keys = [key for key in _translation_cache if key[0] == NLLB_PROVIDER]
        for key in nllb_keys:
            del _translation_cache[key]

    return {
        "ok": True,
        "unloaded": bool(model_path),
        **_nllb_status(model_path),
    }


def _load_nllb_model(model_path: str):
    global _nllb_device, _nllb_model, _nllb_model_path, _nllb_tokenizer

    if ctranslate2 is None or AutoTokenizer is None:
        raise RuntimeError(
            "NLLB INT8 requires ctranslate2, transformers, and sentencepiece. "
            "Restart Forge after installing the extension dependencies."
        )
    if not _nllb_model_is_ready(model_path):
        raise RuntimeError(
            "NLLB INT8 model was not found at "
            + model_path
            + ". Download it from Settings > Prompt Translator or set its path "
            "under Settings > Prompt Translator."
        )

    device = _get_nllb_execution_device()
    with _nllb_lock:
        if (
            _nllb_model is not None
            and _nllb_model_path == model_path
            and _nllb_device == device
        ):
            return _nllb_tokenizer, _nllb_model

        previous_model = _nllb_model
        _nllb_model = None
        _nllb_tokenizer = None
        _nllb_model_path = ""
        _nllb_device = ""
        if previous_model is not None:
            try:
                previous_model.unload_model()
            except Exception:
                pass

        tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
        model = ctranslate2.Translator(
            model_path,
            device=device,
            compute_type="int8_float16" if device == "cuda" else "int8",
        )

        _nllb_tokenizer = tokenizer
        _nllb_model = model
        _nllb_model_path = model_path
        _nllb_device = device
        return tokenizer, model


def _translate_nllb_chunk(
    text: str,
    source_code: str,
    target_code: str,
    tokenizer: object,
    model: object,
) -> str:
    leading_whitespace = text[: len(text) - len(text.lstrip())]
    trailing_whitespace = text[len(text.rstrip()) :]
    text_to_translate = text.strip()
    if not text_to_translate:
        return text

    tokenizer.src_lang = source_code
    source_tokens = tokenizer.convert_ids_to_tokens(tokenizer.encode(text_to_translate))
    result = model.translate_batch(
        [source_tokens],
        target_prefix=[[target_code]],
        beam_size=4,
        max_input_length=512,
        max_decoding_length=512,
    )
    translated_tokens = result[0].hypotheses[0]
    if translated_tokens and translated_tokens[0] == target_code:
        translated_tokens = translated_tokens[1:]
    translated = tokenizer.decode(
        tokenizer.convert_tokens_to_ids(translated_tokens),
        skip_special_tokens=True,
    )
    if not translated:
        raise RuntimeError("NLLB returned an empty result")
    return leading_whitespace + translated + trailing_whitespace


def _translate_with_nllb(text: str, source_name: str, target_name: str) -> str:
    source_code = NLLB_LANGUAGE_CODES.get(source_name)
    target_code = NLLB_LANGUAGE_CODES.get(target_name)
    if not source_code or not target_code:
        supported = ", ".join(NLLB_LANGUAGE_CODES)
        raise RuntimeError(
            "NLLB local provider currently supports: " + supported + "."
        )

    tokenizer, model = _load_nllb_model(_get_nllb_model_path())
    return "".join(
        _translate_nllb_chunk(chunk, source_code, target_code, tokenizer, model)
        for chunk in _split_translation_text(text, NLLB_CHUNK_SIZE)
    )


def _translate_text(text: str, source_name: str, target_name: str) -> TranslateResponse:
    provider = _get_translation_provider()
    if provider == NLLB_PROVIDER:
        source_name = (
            "Auto Detect"
            if source_name in ("auto", "Auto Detect")
            else source_name
            if source_name in NLLB_LANGUAGE_CODES
            else "Auto Detect"
        )
        target_name = (
            target_name if target_name in NLLB_LANGUAGE_CODES else "English"
        )
    else:
        source_name = _normalize_language(source_name, "Auto Detect")
        target_name = _normalize_language(target_name, "English")

    if not text or not text.strip():
        return TranslateResponse(translated_text=text, used_cache=False, ok=True)

    if source_name != "Auto Detect" and source_name == target_name:
        return TranslateResponse(translated_text=text, used_cache=False, ok=True)

    source_code = (
        "auto" if source_name == "Auto Detect" else NLLB_LANGUAGE_CODES[source_name]
    ) if provider == NLLB_PROVIDER else LANGUAGE_CODES[source_name]
    target_code = (
        NLLB_LANGUAGE_CODES[target_name]
        if provider == NLLB_PROVIDER
        else LANGUAGE_CODES[target_name]
    )
    detected_source = ""
    if source_code == "auto" and detect is not None:
        try:
            detected_code = detect(text).lower()
            detected_source = DETECT_TO_LANGUAGE_NAME.get(detected_code, "")
        except LangDetectException:
            detected_source = ""

    effective_source_name = detected_source or source_name
    if provider == NLLB_PROVIDER and source_name == "Auto Detect" and not detected_source:
        return TranslateResponse(
            translated_text=text,
            used_cache=False,
            ok=False,
            error="NLLB could not detect the source language. Select it explicitly.",
        )

    cache_key = (provider, text, source_code, target_code)
    with _cache_lock:
        cached = _translation_cache.get(cache_key)
    if cached is not None:
        return TranslateResponse(
            translated_text=cached,
            used_cache=True,
            ok=True,
            detected_source=detected_source,
        )

    if provider == GOOGLE_PROVIDER and GoogleTranslator is None:
        return TranslateResponse(
            translated_text=text,
            used_cache=False,
            ok=False,
            error="deep-translator is not available",
        )

    try:
        if provider == NLLB_PROVIDER:
            translated = _translate_with_nllb(
                text,
                effective_source_name,
                target_name,
            )
        else:
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
        provider = _get_translation_provider()
        return {
            "default_source_language": _normalize_language(default_source, "Auto Detect"),
            "enabled_languages": [
                language_name
                for language_name in _normalize_enabled_languages(enabled_languages)
                if language_name in (
                    NLLB_LANGUAGE_CODES
                    if provider == NLLB_PROVIDER
                    else SUPPORTED_LANGUAGE_CODES
                )
            ],
            "provider": provider,
        }

    @app.get("/prompt-translator/settings")
    def prompt_translator_settings() -> Dict[str, object]:
        return prompt_translator_settings_payload()

    @app.get("/sdapi/v1/prompt-translator/settings")
    def prompt_translator_settings_sdapi() -> Dict[str, object]:
        return prompt_translator_settings_payload()

    @app.get("/prompt-translator/nllb/status")
    def prompt_translator_nllb_status(model_path: str = "") -> Dict[str, object]:
        return _nllb_status(model_path)

    @app.get("/sdapi/v1/prompt-translator/nllb/status")
    def prompt_translator_nllb_status_sdapi(model_path: str = "") -> Dict[str, object]:
        return _nllb_status(model_path)

    @app.post("/prompt-translator/nllb/download")
    def prompt_translator_nllb_download(payload: NllbDownloadRequest) -> Dict[str, object]:
        return _start_nllb_download(payload.model_path)

    @app.post("/sdapi/v1/prompt-translator/nllb/download")
    def prompt_translator_nllb_download_sdapi(
        payload: NllbDownloadRequest,
    ) -> Dict[str, object]:
        return _start_nllb_download(payload.model_path)

    @app.post("/prompt-translator/nllb/unload")
    def prompt_translator_nllb_unload() -> Dict[str, object]:
        return _unload_nllb_model()

    @app.post("/sdapi/v1/prompt-translator/nllb/unload")
    def prompt_translator_nllb_unload_sdapi() -> Dict[str, object]:
        return _unload_nllb_model()

    @app.post("/prompt-translator/translate", response_model=TranslateResponse)
    def prompt_translator_translate(payload: TranslateRequest) -> TranslateResponse:
        return _translate_text(payload.text, payload.source, payload.target)

    @app.post("/sdapi/v1/prompt-translator/translate", response_model=TranslateResponse)
    def prompt_translator_translate_sdapi(payload: TranslateRequest) -> TranslateResponse:
        return _translate_text(payload.text, payload.source, payload.target)


def _register_settings() -> None:
    section = ("prompt_translator", "Prompt Translator")
    shared.opts.add_option(
        "prompt_translator_provider",
        shared.OptionInfo(
            GOOGLE_PROVIDER,
            "Translation provider",
            gr.Dropdown,
            {"choices": [GOOGLE_PROVIDER, NLLB_PROVIDER]},
            section=section,
        ).needs_reload_ui(),
    )
    shared.opts.add_option(
        "prompt_translator_nllb_device",
        shared.OptionInfo(
            "GPU",
            "NLLB INT8 device",
            gr.Radio,
            {"choices": ["GPU", "CPU"]},
            section=section,
        ),
    )
    shared.opts.add_option(
        "prompt_translator_nllb_model_path",
        shared.OptionInfo(
            NLLB_DEFAULT_MODEL_PATH,
            "NLLB INT8 model path (CTranslate2, about 0.6 GB)",
            gr.Textbox,
            section=section,
        ),
    )
    shared.opts.add_option(
        "prompt_translator_enabled_languages",
        shared.OptionInfo(
            list(DEFAULT_ENABLED_LANGUAGES),
            "Languages shown in the translator interface",
            gr.Dropdown,
            {
                "choices": sorted(INTERFACE_LANGUAGE_NAMES),
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
