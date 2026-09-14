import launch

if not launch.is_installed("deep_translator"):
    launch.run_pip(
        "install deep-translator>=1.11.4",
        "requirements for prompt translator extension",
    )

if not launch.is_installed("langdetect"):
    launch.run_pip(
        "install langdetect>=1.0.9",
        "language detection support for prompt translator extension",
    )

if not launch.is_installed("sentencepiece"):
    launch.run_pip(
        "install sentencepiece>=0.2.0",
        "NLLB tokenizer support for prompt translator extension",
    )

if not launch.is_installed("huggingface_hub"):
    launch.run_pip(
        "install huggingface_hub>=0.24.0",
        "NLLB model download support for prompt translator extension",
    )

if not launch.is_installed("ctranslate2"):
    launch.run_pip(
        "install ctranslate2>=4.8.0",
        "NLLB INT8 inference support for prompt translator extension",
    )
