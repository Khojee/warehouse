"""FlowCore report engine.

Returns Python objects only. No SQL, PDF, or Excel generation yet.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from core.i18n import payment_status_label, stock_status_label
from database import SessionLocal
from models import Product, ProductAlias, Sale

_STOCK_STATUS_ENGLISH: dict[str, str] = {
    "in_stock": "In Stock",
    "low_stock": "Low Stock",
    "out_of_stock": "Out Of Stock",
}

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


def summarize_inventory_report(rows: list[dict[str, Any]]) -> dict[str, str]:
    """Compute summary metrics for an inventory report result set."""
    total_products = len(rows)
    warehouse_value = sum(
        Decimal(str(row.get("inventory_value", "0") or "0")) for row in rows
    )
    low_stock_count = sum(1 for row in rows if row.get("status_code") == "low_stock")
    out_of_stock_count = sum(
        1 for row in rows if row.get("status_code") == "out_of_stock"
    )
    return {
        "total_products": str(total_products),
        "warehouse_value": f"{warehouse_value:.2f}",
        "low_stock_count": str(low_stock_count),
        "out_of_stock_count": str(out_of_stock_count),
    }


def _inventory_stock_status(quantity: int, min_stock: int) -> tuple[str, str]:
    if quantity <= 0:
        status_code = "out_of_stock"
    elif quantity <= max(min_stock, 0):
        status_code = "low_stock"
    else:
        status_code = "in_stock"
    return status_code, stock_status_label(_STOCK_STATUS_ENGLISH[status_code])


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
    del date_from, date_to
    active_filters = filters or {}
    search = str(active_filters.get("search", "") or "").strip()
    category_id = str(active_filters.get("category_id", "") or "").strip()
    size = str(active_filters.get("size", "") or "").strip()
    pressure = str(active_filters.get("pressure", "") or "").strip()
    stock_status = str(active_filters.get("stock_status", "") or "").strip()

    with SessionLocal() as session:
        stmt = (
            select(Product)
            .options(selectinload(Product.product_category), selectinload(Product.inventory))
            .order_by(Product.name.asc())
        )
        if search:
            term = f"%{search}%"
            alias_product_ids = select(ProductAlias.product_id).where(
                ProductAlias.alias.ilike(term)
            )
            stmt = stmt.where(or_(Product.name.ilike(term), Product.id.in_(alias_product_ids)))
        if category_id:
            stmt = stmt.where(Product.category_id == int(category_id))
        if size:
            stmt = stmt.where(Product.size == size)
        if pressure:
            stmt = stmt.where(Product.pressure == pressure)

        products = session.scalars(stmt).all()

    rows: list[dict[str, Any]] = []
    for product in products:
        quantity = product.inventory.quantity if product.inventory is not None else 0
        status_code, status_label = _inventory_stock_status(quantity, product.min_stock)
        if stock_status == "in_stock" and status_code != "in_stock":
            continue
        if stock_status == "low_stock" and status_code != "low_stock":
            continue
        if stock_status == "out_of_stock" and status_code != "out_of_stock":
            continue

        inventory_value = (Decimal(quantity) * product.current_price).quantize(Decimal("0.01"))
        rows.append(
            {
                "product_id": product.id,
                "product": product.name,
                "category": (
                    product.product_category.name
                    if product.product_category is not None
                    else (product.category or "")
                ),
                "size": product.size or "",
                "pressure": product.pressure or "",
                "quantity": quantity,
                "unit_price": f"{product.current_price:.2f}",
                "inventory_value": f"{inventory_value:.2f}",
                "status": status_label,
                "status_code": status_code,
            }
        )
    return rows


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
