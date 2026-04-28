"""
Vorte i18n Module
==================
Full internationalization support with auto language detection,
locale-aware formatting, and JSON-based translations.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request

from vorte.core.module import Module, ModuleMeta, ModulePriority
from vorte.core.response import success_response


class Translator:
    """Manages translations and locale-aware formatting."""

    def __init__(self, locales_dir: str = "locales", default_locale: str = "en", fallback_locale: str = "en"):
        self._locales_dir = Path(locales_dir)
        self._default_locale = default_locale
        self._fallback_locale = fallback_locale
        self._translations: Dict[str, Dict[str, str]] = {}
        self._load_translations()

    def _load_translations(self) -> None:
        """Load all translation files from the locales directory."""
        if not self._locales_dir.exists():
            return
        for locale_file in self._locales_dir.glob("*.json"):
            locale_name = locale_file.stem
            try:
                with open(locale_file, "r", encoding="utf-8") as f:
                    self._translations[locale_name] = json.load(f)
            except (json.JSONDecodeError, IOError):
                continue

    def t(self, key: str, locale: Optional[str] = None, **kwargs) -> str:
        """Translate a key to the given locale with interpolation."""
        locale = locale or self._default_locale
        translations = self._translations.get(locale, {})
        text = translations.get(key)
        if text is None:
            # Try fallback
            translations = self._translations.get(self._fallback_locale, {})
            text = translations.get(key, key)
        if kwargs:
            try:
                text = text.format(**kwargs)
            except (KeyError, IndexError):
                pass
        return text

    def currency(self, amount: float, locale: Optional[str] = None) -> str:
        """Format a number as currency."""
        locale = locale or self._default_locale
        locale_map = {"en": ("en_US", "USD"), "sw": ("sw_KE", "KES"), "fr": ("fr_FR", "EUR")}
        loc, curr = locale_map.get(locale, ("en_US", "USD"))
        try:
            import locale as pylocale
            pylocale.setlocale(pylocale.LC_ALL, loc)
            return f"{curr} {amount:,.2f}"
        except Exception:
            return f"{amount:.2f}"

    def date(self, dt, locale: Optional[str] = None) -> str:
        """Format a datetime according to locale."""
        locale = locale or self._default_locale
        months_en = ["January","February","March","April","May","June","July","August","September","October","November","December"]
        months_sw = ["Januari","Februari","Machi","Aprili","Mei","Juni","Julai","Agosti","Septemba","Oktoba","Novemba","Desemba"]
        months = months_sw if locale == "sw" else months_en
        return f"{dt.day} {months[dt.month - 1]} {dt.year}"

    def number(self, value: float, locale: Optional[str] = None) -> str:
        """Format a number according to locale conventions."""
        locale = locale or self._default_locale
        if locale == "en_IN":
            # Indian numbering system
            s = f"{value:,.2f}"
            parts = s.split(".")
            int_part = parts[0]
            if len(int_part) > 3:
                last_three = int_part[-3:]
                rest = int_part[:-3]
                formatted = ""
                while rest:
                    chunk = rest[-2:] if len(rest) > 2 else rest
                    formatted = f",{chunk}{formatted}"
                    rest = rest[:-2]
                return f"{formatted}{last_three}.{parts[1]}"
            return s
        return f"{value:,.2f}"

    def detect_language(self, accept_language: str) -> str:
        """Detect language from Accept-Language header."""
        if not accept_language:
            return self._default_locale
        languages = [lang.split(";")[0].strip() for lang in accept_language.split(",")]
        for lang in languages:
            code = lang.split("-")[0].lower()
            if code in self._translations:
                return code
        return self._default_locale

    def add_locale(self, locale: str, translations: Dict[str, str]) -> None:
        """Add or update translations for a locale."""
        if locale in self._translations:
            self._translations[locale].update(translations)
        else:
            self._translations[locale] = translations

    def get_available_locales(self) -> List[str]:
        """Get all available locales."""
        return list(self._translations.keys())


class I18nModule(Module):
    """
    Internationalization module with auto language detection and locale formatting.
    
    Usage:
        app.register(I18nModule(default_locale='en', locales_dir='locales'))
    """

    meta = ModuleMeta(
        name="i18n",
        version="1.0.0",
        description="Internationalization with auto language detection and locale formatting",
        priority=ModulePriority.ROUTES,
    )

    def __init__(self, *, default_locale: str = "en", fallback_locale: str = "en", locales_dir: str = "locales"):
        super().__init__(default_locale=default_locale, fallback_locale=fallback_locale, locales_dir=locales_dir)
        self._translator: Optional[Translator] = None

    def register(self, app) -> None:
        self._translator = Translator(
            locales_dir=self.get_config("locales_dir", "locales"),
            default_locale=self.get_config("default_locale", "en"),
            fallback_locale=self.get_config("fallback_locale", "en"),
        )
        if hasattr(app, 'container'):
            app.container.register_instance(Translator, self._translator)

    @property
    def t(self) -> Translator:
        return self._translator
