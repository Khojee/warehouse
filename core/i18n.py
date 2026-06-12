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
DEFAULT_LOCALE = "uz"
FALLBACK_LOCALE = "en"

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
    if text is None and _current_locale != FALLBACK_LOCALE:
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


_PAYMENT_STATUS_KEYS: dict[str, str] = {
    "Paid": "status.payment.paid",
    "Partially Paid": "status.payment.partially_paid",
    "Unpaid": "status.payment.unpaid",
}

_STOCK_STATUS_KEYS: dict[str, str] = {
    "In Stock": "status.stock.in_stock",
    "Low Stock": "status.stock.low_stock",
    "Out Of Stock": "status.stock.out_of_stock",
    "Normal": "status.stock.normal",
}

_DEBT_STATUS_KEYS: dict[str, str] = {
    "Active": "status.debt.active",
    "Paid": "status.debt.paid",
    "Overdue": "status.debt.overdue",
    "Open": "status.debt.active",
}

_MOVEMENT_TYPE_KEYS: dict[str, str] = {
    "IN": "status.movement.in",
    "OUT": "status.movement.out",
}


def payment_status_label(value: str) -> str:
    """Translate a stored payment status value for display."""
    key = _PAYMENT_STATUS_KEYS.get(value or "")
    return t(key) if key else (value or "")


def stock_status_label(value: str) -> str:
    """Translate a stock status value for display."""
    key = _STOCK_STATUS_KEYS.get(value or "")
    return t(key) if key else (value or "")


def debt_status_label(value: str) -> str:
    """Translate a debt status value for display."""
    key = _DEBT_STATUS_KEYS.get(value or "")
    return t(key) if key else (value or "")


def movement_type_label(value: str) -> str:
    """Translate a stock movement type for display."""
    key = _MOVEMENT_TYPE_KEYS.get(value or "")
    return t(key) if key else (value or "")


def badge_success_values() -> list[str]:
    """Return localized status strings that render as success badges."""
    return [
        t("status.payment.paid"),
        t("status.stock.in_stock"),
        t("status.stock.normal"),
        t("status.movement.in"),
        t("status.debt.paid"),
    ]


def badge_warning_values() -> list[str]:
    """Return localized status strings that render as warning badges."""
    return [
        t("status.payment.partially_paid"),
        t("status.stock.low_stock"),
        t("status.debt.active"),
    ]


def badge_danger_values() -> list[str]:
    """Return localized status strings that render as danger badges."""
    return [
        t("status.payment.unpaid"),
        t("status.stock.out_of_stock"),
        t("status.debt.overdue"),
        t("status.movement.out"),
    ]
