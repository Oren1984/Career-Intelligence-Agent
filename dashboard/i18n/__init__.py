"""Centralised UI translations (English + Hebrew).

Strings live in en.yaml / he.yaml under dotted keys. English is the reference
language: a key missing from Hebrew falls back to English, and a key missing
everywhere renders as the key itself (tests fail on both).

    t("nav.dashboard")                  -> "Dashboard" / "דשבורד"
    t("classic.count", n=5)             -> "5 jobs shown"
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

LANGUAGES = {"en": "English", "he": "עברית"}
DEFAULT_LANGUAGE = "en"
RTL_LANGUAGES = {"he"}

_DIR = Path(__file__).resolve().parent


def _flatten(data: dict, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in (data or {}).items():
        full = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(_flatten(value, f"{full}."))
        else:
            out[full] = str(value)
    return out


@lru_cache(maxsize=None)
def catalog(lang: str) -> dict[str, str]:
    path = _DIR / f"{lang}.yaml"
    with open(path, "r", encoding="utf-8") as fh:
        return _flatten(yaml.safe_load(fh))


def translate(lang: str, key: str, **params) -> str:
    text = catalog(lang).get(key) or catalog(DEFAULT_LANGUAGE).get(key) or key
    return text.format(**params) if params else text


def normalize_language(lang: str | None) -> str:
    return lang if lang in LANGUAGES else DEFAULT_LANGUAGE


def is_rtl(lang: str) -> bool:
    return lang in RTL_LANGUAGES
