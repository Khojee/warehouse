"""FlowCore report engine.

Returns Python objects only. No SQL, PDF, or Excel generation yet.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.i18n import payment_status_label
from database import SessionLocal
from models import Sale

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


def summarize_sales_report(rows: list[dict[str, Any]]) -> dict[str, str]:
    """Compute summary metrics for a sales report result set."""
    total_sales = len(rows)
    total_revenue = sum(Decimal(str(row.get("total_amount", "0") or "0")) for row in rows)
    paid_amount = sum(Decimal(str(row.get("paid_amount", "0") or "0")) for row in rows)
    outstanding_debt = sum(
        Decimal(str(row.get("remaining_amount", "0") or "0")) for row in rows
    )
    return {
        "total_sales": str(total_sales),
        "total_revenue": f"{total_revenue:.2f}",
        "paid_amount": f"{paid_amount:.2f}",
        "outstanding_debt": f"{outstanding_debt:.2f}",
    }


def _parse_date_bound(value: str | None, *, end_of_day: bool = False) -> datetime | None:
    if value is None or not str(value).strip():
        return None
    try:
        parsed = datetime.strptime(str(value).strip(), "%Y-%m-%d")
    except ValueError:
        return None
    if end_of_day:
        return parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
    return parsed.replace(hour=0, minute=0, second=0, microsecond=0)


def _generate_sales_report(
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    del filters
    start = _parse_date_bound(date_from)
    end = _parse_date_bound(date_to, end_of_day=True)

    with SessionLocal() as session:
        stmt = (
            select(Sale)
            .options(selectinload(Sale.customer), selectinload(Sale.items))
            .order_by(Sale.sale_date.desc(), Sale.id.desc())
        )
        if start is not None:
            stmt = stmt.where(Sale.sale_date >= start)
        if end is not None:
            stmt = stmt.where(Sale.sale_date <= end)
        sales = session.scalars(stmt).all()

    return [
        {
            "sale_number": sale.sale_number,
            "date": sale.sale_date.strftime("%Y-%m-%d"),
            "customer": sale.customer.full_name if sale.customer else "",
            "items_count": len(sale.items),
            "total_amount": f"{sale.total_amount:.2f}",
            "paid_amount": f"{sale.paid_amount:.2f}",
            "remaining_amount": f"{sale.remaining_amount:.2f}",
            "payment_type": sale.payment_type or "",
            "status": payment_status_label(sale.payment_status or ""),
        }
        for sale in sales
    ]


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
