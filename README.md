# Prompt Translator for Forge NEO / Stable Diffusion WebUI

Translate your **positive prompt** inside Forge NEO / A1111 WebUI with one key press or live auto-translation.

<img width="923" height="308" alt="47567" src="https://github.com/user-attachments/assets/342c8d23-5514-4c78-9f2b-8dfdc2c438c6" />

## Features

- Works in both `txt2img` and `img2img`
- Adds a compact translator row near prompt fields
- `From` language supports `Auto Detect`
- `To` language defaults to `English`
- `Alt+Q` translates current positive prompt instantly
- `Alt+W` swaps `From` and `To`
- Optional **Auto Translate** mode with debounce (`900 ms`)
- Translation runs only for **positive prompt** (negative prompt is untouched)
- Safe fallback on translation errors (generation should not break)
- In-memory translation cache on backend

## Supported Languages

- Auto Detect (From only)
- Russian
- English
- Chinese
- Japanese
- Korean
- German
- French
- Spanish
- Italian
- Portuguese

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
- `From`: Auto Detect
- `To`: English

Typical flow:
1. Type prompt in your language.
2. Press `Alt+Q` to translate once.
3. Or enable **Auto Translate** for live translation while typing.
4. Use `Alt+W` or the swap button to swap languages.

## Notes on Auto Detect

In Auto Translate mode, detected source language is remembered during the session to keep mixed prompt edits translating reliably.

## Limitations

- This version does not yet protect advanced prompt tokens such as LoRA tags / weight groups with placeholders.
- Live translation sends frequent network requests depending on typing speed.

## License

Add your preferred license here (for example, MIT).
