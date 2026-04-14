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
