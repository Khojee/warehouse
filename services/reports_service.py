"""FlowCore report engine.

Returns Python objects only. No SQL, PDF, or Excel generation yet.
"""

from __future__ import annotations

from typing import Any, Callable

REPORT_TYPES: tuple[str, ...] = (
    "sales",
    "purchases",
    "inventory",
    "debtors",
    "product_sales",
    "suppliers",
    "customers",
    "stock_movements",
)


def generate_report(
    report_type: str,
    date_from: str | None = None,
    date_to: str | None = None,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Dispatch to a report generator and return rows as Python objects."""
    generators: dict[str, Callable[..., list[dict[str, Any]]]] = {
        "sales": _generate_sales_report,
        "purchases": _generate_purchase_report,
        "inventory": _generate_inventory_report,
        "debtors": _generate_debtors_report,
        "product_sales": _generate_product_sales_report,
        "suppliers": _generate_supplier_report,
        "customers": _generate_customer_report,
        "stock_movements": _generate_stock_movement_report,
    }

    key = (report_type or "").strip().lower()
    generator = generators.get(key)
    if generator is None:
        raise ValueError(f"Unsupported report type: {report_type}")

    return generator(date_from=date_from, date_to=date_to, filters=filters or {})


def _generate_sales_report(
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    del date_from, date_to, filters
    return []


def _generate_purchase_report(
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    del date_from, date_to, filters
    return []


def _generate_inventory_report(
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    del date_from, date_to, filters
    return []


def _generate_debtors_report(
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    del date_from, date_to, filters
    return []


def _generate_product_sales_report(
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    del date_from, date_to, filters
    return []


def _generate_supplier_report(
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    del date_from, date_to, filters
    return []


def _generate_customer_report(
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    del date_from, date_to, filters
    return []


def _generate_stock_movement_report(
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    del date_from, date_to, filters
    return []
