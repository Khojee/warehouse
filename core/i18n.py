"""FlowCore internationalization infrastructure.

Usage (future integration)::

    from core.i18n import t, set_locale

    set_locale("uz")
    label = t("common.button.save")
    message = t("sales.notify.created", sale_number="S-001")

This module does not modify any UI yet — it only loads catalogs and exposes
translation helpers.
"""

from __future__ import annotations

from typing import Any

from locales.en import MESSAGES as EN_MESSAGES
from locales.uz import MESSAGES as UZ_MESSAGES

SUPPORTED_LOCALES: tuple[str, ...] = ("en", "uz")
DEFAULT_LOCALE = "en"

_CATALOGS: dict[str, dict[str, str]] = {
    "en": EN_MESSAGES,
    "uz": UZ_MESSAGES,
}

_current_locale: str = DEFAULT_LOCALE


def get_locale() -> str:
    """Return the active locale code."""
    return _current_locale


def set_locale(locale: str) -> None:
    """Switch the active locale. Raises ValueError for unsupported codes."""
    normalized = (locale or "").strip().lower()
    if normalized not in _CATALOGS:
        supported = ", ".join(SUPPORTED_LOCALES)
        raise ValueError(f"Unsupported locale '{locale}'. Supported: {supported}")
    global _current_locale
    _current_locale = normalized


def available_locales() -> tuple[str, ...]:
    """Return locale codes that have a loaded catalog."""
    return SUPPORTED_LOCALES


def get_catalog(locale: str | None = None) -> dict[str, str]:
    """Return the full message catalog for a locale (defaults to active)."""
    code = (locale or _current_locale).strip().lower()
    return _CATALOGS.get(code, EN_MESSAGES)


def t(key: str, /, **kwargs: Any) -> str:
    """Translate *key* using the active locale catalog.

    Missing keys fall back to English, then to the key itself.
    Placeholders use ``str.format`` syntax: ``t("greet", name="Ada")``.
    """
    catalog = get_catalog()
    text = catalog.get(key)
    if text is None and _current_locale != DEFAULT_LOCALE:
        text = EN_MESSAGES.get(key)
    if text is None:
        text = key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text
    return text


def has_key(key: str, locale: str | None = None) -> bool:
    """Return True if *key* exists in the given locale catalog."""
    return key in get_catalog(locale)
