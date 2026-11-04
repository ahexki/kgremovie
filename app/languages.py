"""Source languages of the dub (every one is translated INTO Burmese). One table for the planner and the window.

The speech is read by local Whisper, so the list is the languages Whisper knows well. "auto" lets Whisper detect the
language of each video. Burmese itself is not in the list: Whisper cannot recognise Burmese speech reliably.

label        : what the dropdown shows ("<label> → Myanmar")
name         : the language name written into the AI prompts
nospace      : written without spaces between words (Whisper hands back pieces that are joined without a space)
"""
from __future__ import annotations

LANGS: dict[str, dict] = {
    "auto": {"name": "Auto-detect", "label": "Auto-detect (Whisper)", "nospace": False},
    "en": {"name": "English", "label": "English", "nospace": False},
    "zh": {"name": "Chinese (Mandarin)", "label": "Chinese 中文", "nospace": True},
    "ja": {"name": "Japanese", "label": "Japanese 日本語", "nospace": True},
    "ko": {"name": "Korean", "label": "Korean 한국어", "nospace": False},
    "th": {"name": "Thai", "label": "Thai ไทย", "nospace": True},
    "vi": {"name": "Vietnamese", "label": "Vietnamese Tiếng Việt", "nospace": False},
    "id": {"name": "Indonesian", "label": "Indonesian", "nospace": False},
    "ms": {"name": "Malay", "label": "Malay", "nospace": False},
    "tl": {"name": "Filipino (Tagalog)", "label": "Filipino (Tagalog)", "nospace": False},
    "hi": {"name": "Hindi", "label": "Hindi हिन्दी", "nospace": False},
    "bn": {"name": "Bengali", "label": "Bengali বাংলা", "nospace": False},
    "ur": {"name": "Urdu", "label": "Urdu اردو", "nospace": False},
    "ar": {"name": "Arabic", "label": "Arabic العربية", "nospace": False},
    "tr": {"name": "Turkish", "label": "Turkish Türkçe", "nospace": False},
    "ru": {"name": "Russian", "label": "Russian Русский", "nospace": False},
    "es": {"name": "Spanish", "label": "Spanish Español", "nospace": False},
    "fr": {"name": "French", "label": "French Français", "nospace": False},
    "de": {"name": "German", "label": "German Deutsch", "nospace": False},
    "pt": {"name": "Portuguese", "label": "Portuguese Português", "nospace": False},
    "it": {"name": "Italian", "label": "Italian Italiano", "nospace": False},
}

# Names for the codes Whisper may detect in "auto" mode that are not in the dropdown.
EXTRA_NAMES = {
    "nl": "Dutch", "pl": "Polish", "uk": "Ukrainian", "cs": "Czech", "sv": "Swedish", "el": "Greek", "he": "Hebrew",
    "fa": "Persian", "ta": "Tamil", "te": "Telugu", "ne": "Nepali", "si": "Sinhala", "km": "Khmer", "lo": "Lao",
    "ro": "Romanian", "hu": "Hungarian", "da": "Danish", "fi": "Finnish", "no": "Norwegian", "sw": "Swahili",
}

SOURCE_DIRECTION_LABEL = "→ Myanmar"


def language_name(code: str) -> str:
    code = str(code or "").strip().lower()
    if code in LANGS:
        return LANGS[code]["name"]
    return EXTRA_NAMES.get(code, code.upper() or "Unknown")


def dropdown_labels() -> dict[str, str]:
    """{"English → Myanmar": "en", ...} in dropdown order."""
    return {f"{info['label']} {SOURCE_DIRECTION_LABEL}": code for code, info in LANGS.items()}
