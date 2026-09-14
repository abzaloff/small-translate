# Prompt Translator for Forge NEO / Stable Diffusion WebUI

Translate your **positive prompt** inside Forge NEO / A1111 WebUI with one key press or live auto-translation.

<img width="923" height="308" alt="47567" src="https://github.com/user-attachments/assets/342c8d23-5514-4c78-9f2b-8dfdc2c438c6" />

## Features

- Works in both `txt2img` and `img2img`
- Adds a compact translator row near prompt fields
- `From` language supports `Auto Detect`
- Configurable interface languages and default `From` language in Forge settings
- `To` language defaults to `English`
- `Alt+Q` translates current positive prompt instantly
- `Alt+W` swaps `From` and `To`
- Optional **Auto Translate** mode with debounce (`900 ms`)
- Translation runs only for **positive prompt** (negative prompt is untouched)
- Safe fallback on translation errors (generation should not break)
- In-memory translation cache on backend
- Optional local **NLLB-200** provider for offline translation

## Supported Languages

The Google translator backend exposes 133 language variants. Choose any number of
them under `Settings -> Prompt Translator -> Languages shown in the translator
interface`. The ten languages enabled by default are Russian, English, Chinese,
Japanese, Korean, German, French, Spanish, Italian, and Portuguese.

`Default source language` can independently use any supported language or
`Auto Detect`. A default source language that is not in the interface selection
is still added to the `From` list so that the configured default remains usable.

## Project Structure

```text
extensions/prompt-translator/
|-- scripts/
|   `-- prompt_translator.py
|-- javascript/
|   `-- prompt_translator.js
|-- style.css
|-- requirements.txt
|-- install.py
`-- README.md
```

## Installation

1. Copy this folder to your WebUI extensions directory:
   - `stable-diffusion-webui/extensions/prompt-translator`
2. Restart Forge NEO / WebUI.
3. Dependencies are installed through `install.py` (`deep-translator`, `langdetect`).

Alternative (recommended for GitHub users):
1. Open WebUI -> `Extensions` tab -> `Install from URL`.
2. Paste repository URL:
   - `https://github.com/abzaloff/small-translate.git`
3. Click `Install`, then restart Forge NEO / WebUI.

## Usage

Default state on each Forge UI load:
- `Auto Translate`: OFF
- `From`: Forge setting `Prompt Translator -> Default source language` (`Auto Detect` by default)
- `To`: English when enabled, otherwise the first selected interface language

Typical flow:
1. Type prompt in your language.
2. Press `Alt+Q` to translate once.
3. Or enable **Auto Translate** for live translation while typing.
4. Use `Alt+W` or the swap button to swap languages.

## Notes on Auto Detect

In Auto Translate mode, detected source language is remembered during the session to keep mixed prompt edits translating reliably.

## Local NLLB-200 provider

Google remains the default provider. To translate without a network connection,
open `Settings -> Prompt Translator`, select `NLLB-200 (local)` and click
`Download NLLB INT8 model (0.6 GB)`. The extension downloads a CTranslate2
INT8 conversion of the NLLB-200 600M model from
[`JustFrederik/nllb-200-distilled-600M-ct2-int8`](https://huggingface.co/JustFrederik/nllb-200-distilled-600M-ct2-int8)
and shows the progress. No Hugging Face account or manual file copy is required.

By default the model is saved to
`Forge/models/prompt-translator/nllb-200-distilled-600M-ct2-int8`. Change
`NLLB local model path` before pressing the download button if another drive
should hold the model. Click Forge's `Apply settings` after selecting the
provider or changing this path, so the choice is retained for translation.

`NLLB INT8 device` lets the user choose `GPU` (the default) or `CPU`. When the
choice changes, the next local translation reloads the model on that device.

`Unload NLLB from memory` frees RAM/VRAM while keeping the downloaded files.
The next local translation loads the model again.

The local provider currently supports the default translator languages: Russian,
English, Chinese, Japanese, Korean, German, French, Spanish, Italian, and
Portuguese. It loads the model only on the first local translation and keeps it
in memory for later requests. The INT8 download is a third-party CTranslate2
conversion of Meta's NLLB model, licensed under CC-BY-NC 4.0; review its model
card before using it outside personal or non-commercial work.

## Limitations

- This version does not yet protect advanced prompt tokens such as LoRA tags / weight groups with placeholders.
- Live translation sends frequent network requests depending on typing speed.
- NLLB is a local research model rather than a certified translation service;
  long prompts are split into smaller chunks before translation.

## License

See [LICENSE.md](./LICENSE.md).
