"""
Translation helper module for AudioBookConverter.
Provides the tr() function for translating UI strings.
"""
import json
import locale
from pathlib import Path
from typing import Any, Optional

_i18n_dir = Path(__file__).parent
_translations: dict[str, dict] = {}
_current_language: str = "en"


def get_system_language() -> str:
    """Detect system language and return 'en' or 'ru'."""
    try:
        lang = locale.getdefaultlocale()[0]
        if lang and lang.lower().startswith("ru"):
            return "ru"
    except Exception:
        pass
    return "en"


def load_translations(lang: str) -> dict:
    """Load translations from JSON file."""
    file_path = _i18n_dir / f"{lang}.json"
    if file_path.exists():
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    # Fallback to English
    fallback_path = _i18n_dir / "en.json"
    if fallback_path.exists():
        with open(fallback_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def set_language(lang: str) -> bool:
    """Set the current language for translations."""
    global _current_language, _translations
    if lang in ("en", "ru"):
        _translations = load_translations(lang)
        _current_language = lang
        return True
    return False


def get_language() -> str:
    """Get the current language code."""
    return _current_language


def get_available_languages() -> list[str]:
    """Get list of available language codes."""
    return ["en", "ru"]


def get_language_name(lang: str) -> str:
    """Get the display name for a language code."""
    names = {
        "en": "English",
        "ru": "Русский"
    }
    return names.get(lang, lang)


def tr(key: str, **kwargs: Any) -> str:
    """
    Translate a key to the current language.

    Args:
        key: Dot-separated key path (e.g., "menu.file")
        **kwargs: Format arguments for the string

    Returns:
        Translated string, or the key if not found
    """
    global _translations, _current_language

    # Ensure translations are loaded
    if not _translations:
        _translations = load_translations(_current_language)

    # Navigate the nested dictionary
    parts = key.split(".")
    value: Any = _translations

    for part in parts:
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            # Key not found, return the key itself
            return key

    if not isinstance(value, str):
        return key

    # Format the string with any provided kwargs
    try:
        return value.format(**kwargs)
    except (KeyError, ValueError):
        return value


class Translator:
    """Class-based translator for Qt integration."""

    def __init__(self):
        self._lang = get_system_language()
        self._translations: dict = {}
        self.load(self._lang)

    def load(self, lang: str) -> None:
        """Load translations for the specified language."""
        self._lang = lang
        self._translations = load_translations(lang)

    @property
    def language(self) -> str:
        return self._lang

    @language.setter
    def language(self, lang: str) -> None:
        self.load(lang)

    def translate(self, key: str, **kwargs: Any) -> str:
        """Translate a key with optional format arguments."""
        parts = key.split(".")
        value: Any = self._translations

        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return key

        if not isinstance(value, str):
            return key

        try:
            return value.format(**kwargs)
        except (KeyError, ValueError):
            return value

    def __call__(self, key: str, **kwargs: Any) -> str:
        """Allow calling the translator directly."""
        return self.translate(key, **kwargs)


# Initialize on module load
_translations = load_translations(_current_language)
