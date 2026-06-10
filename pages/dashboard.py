from __future__ import annotations

from decimal import Decimal
from typing import Any

from nicegui import ui
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from database import SessionLocal
from models import Debtor, Inventory, Product, Purchase, Sale
from pages.layout import with_master_layout


def load_dashboard_data() -> dict[str, Any]:
    with SessionLocal() as session:
        total_products = session.scalar(select(func.count(Product.id))) or 0

        inventory_value_raw = session.scalar(
            select(
                func.coalesce(
                    func.sum(
                        func.coalesce(Inventory.quantity, 0)
                        * func.coalesce(Product.current_price, 0)
                    ),
                    0,
                )
            ).select_from(Product).outerjoin(Inventory, Inventory.product_id == Product.id)
        ) or Decimal("0.00")

        total_quantity_raw = session.scalar(
            select(func.coalesce(func.sum(Inventory.quantity), 0))
        ) or 0

        low_stock_count = session.scalar(
            select(func.count(Product.id))
            .select_from(Product)
            .outerjoin(Inventory, Inventory.product_id == Product.id)
            .where(Product.min_stock > 0)
            .where(func.coalesce(Inventory.quantity, 0) < Product.min_stock)
        ) or 0

        active_debtors = session.scalar(
            select(func.count(Debtor.id)).where(Debtor.remaining_amount > Decimal("0.00"))
        ) or 0
        outstanding_debt_raw = session.scalar(
            select(func.coalesce(func.sum(Debtor.remaining_amount), 0)).where(
                Debtor.remaining_amount > Decimal("0.00")
            )
        ) or Decimal("0.00")

        recent_sales_models = session.scalars(
            select(Sale)
            .options(selectinload(Sale.customer))
            .order_by(Sale.sale_date.desc(), Sale.id.desc())
            .limit(10)
        ).all()
        recent_sales = [
            {
                "sale_number": sale.sale_number,
                "date": sale.sale_date.strftime("%Y-%m-%d"),
                "customer": sale.customer.full_name if sale.customer else "-",
                "total_amount": f"{sale.total_amount:.2f}",
                "status": sale.payment_status or "",
            }
            for sale in recent_sales_models
        ]

        recent_purchases_models = session.scalars(
            select(Purchase)
            .options(selectinload(Purchase.supplier))
            .order_by(Purchase.purchase_date.desc(), Purchase.id.desc())
            .limit(10)
        ).all()
        recent_purchases = [
            {
                "purchase_number": purchase.purchase_number,
                "date": purchase.purchase_date.strftime("%Y-%m-%d"),
                "supplier": purchase.supplier.company_name if purchase.supplier else "-",
                "total_amount": f"{purchase.total_amount:.2f}",
                "status": purchase.payment_status or "",
            }
            for purchase in recent_purchases_models
        ]

        low_stock_models = session.scalars(
            select(Product)
            .options(selectinload(Product.inventory))
            .order_by(Product.name.asc())
        ).all()
        low_stock_rows: list[dict[str, Any]] = []
        for product in low_stock_models:
            quantity = product.inventory.quantity if product.inventory is not None else 0
            if product.min_stock > 0 and quantity < product.min_stock:
                low_stock_rows.append(
                    {
                        "product_name": product.name,
                        "quantity": quantity,
                        "min_stock": product.min_stock,
                        "unit": product.unit,
                    }
                )

    return {
        "cards": {
            "total_products": str(int(total_products)),
            "inventory_value": f"{Decimal(inventory_value_raw):.2f}",
            "total_quantity": str(int(total_quantity_raw)),
            "low_stock_count": str(int(low_stock_count)),
            "active_debtors": str(int(active_debtors)),
            "outstanding_debt": f"{Decimal(outstanding_debt_raw):.2f}",
        },
        "recent_sales": recent_sales,
        "recent_purchases": recent_purchases,
        "low_stock_products": low_stock_rows,
    }


@ui.page("/")
def home_page() -> None:
    ui.navigate.to("/dashboard")


@ui.page("/dashboard")
@with_master_layout("Dashboard")
def dashboard_page() -> None:
    ui.label("Dashboard").classes("text-h4 q-mb-md")

    with ui.row().classes("w-full items-stretch q-gutter-sm q-mb-md"):
        with ui.card().classes("flex-1 min-w-[180px] q-pa-md"):
            total_products_label = ui.label("0").classes("text-h4 text-weight-bold text-center")
            ui.label("Total Products").classes("text-subtitle2 text-grey-8 text-center")
        with ui.card().classes("flex-1 min-w-[180px] q-pa-md"):
            inventory_value_label = ui.label("0.00").classes("text-h4 text-weight-bold text-center")
            ui.label("Inventory Value").classes("text-subtitle2 text-grey-8 text-center")
        with ui.card().classes("flex-1 min-w-[180px] q-pa-md"):
            total_quantity_label = ui.label("0").classes("text-h4 text-weight-bold text-center")
            ui.label("Total Quantity In Stock").classes("text-subtitle2 text-grey-8 text-center")

    with ui.row().classes("w-full items-stretch q-gutter-sm q-mb-md"):
        with ui.card().classes("flex-1 min-w-[180px] q-pa-md"):
            low_stock_count_label = ui.label("0").classes("text-h4 text-weight-bold text-center")
            ui.label("Low Stock Count").classes("text-subtitle2 text-grey-8 text-center")
        with ui.card().classes("flex-1 min-w-[180px] q-pa-md"):
            active_debtors_label = ui.label("0").classes("text-h4 text-weight-bold text-center")
            ui.label("Active Debtors").classes("text-subtitle2 text-grey-8 text-center")
        with ui.card().classes("flex-1 min-w-[180px] q-pa-md"):
            outstanding_debt_label = ui.label("0.00").classes("text-h4 text-weight-bold text-center")
            ui.label("Outstanding Debt").classes("text-subtitle2 text-grey-8 text-center")

    recent_sales_columns = [
        {"name": "sale_number", "label": "Sale Number", "field": "sale_number", "align": "left"},
        {"name": "date", "label": "Date", "field": "date", "align": "left"},
        {"name": "customer", "label": "Customer", "field": "customer", "align": "left"},
        {"name": "total_amount", "label": "Total Amount", "field": "total_amount", "align": "right"},
        {"name": "status", "label": "Status", "field": "status", "align": "center"},
    ]
    recent_purchases_columns = [
        {"name": "purchase_number", "label": "Purchase Number", "field": "purchase_number", "align": "left"},
        {"name": "date", "label": "Date", "field": "date", "align": "left"},
        {"name": "supplier", "label": "Supplier", "field": "supplier", "align": "left"},
        {"name": "total_amount", "label": "Total Amount", "field": "total_amount", "align": "right"},
        {"name": "status", "label": "Status", "field": "status", "align": "center"},
    ]
    low_stock_columns = [
        {"name": "product_name", "label": "Product", "field": "product_name", "align": "left"},
        {"name": "quantity", "label": "Quantity", "field": "quantity", "align": "right"},
        {"name": "min_stock", "label": "Min Stock", "field": "min_stock", "align": "right"},
        {"name": "unit", "label": "Unit", "field": "unit", "align": "left"},
    ]

    with ui.card().classes("w-full q-pa-md q-mb-md"):
        ui.label("Recent Sales").classes("text-h6 q-mb-sm")
        recent_sales_table = ui.table(
            columns=recent_sales_columns,
            rows=[],
            row_key="sale_number",
            pagination=10,
        ).classes("w-full")

    with ui.card().classes("w-full q-pa-md q-mb-md"):
        ui.label("Recent Purchases").classes("text-h6 q-mb-sm")
        recent_purchases_table = ui.table(
            columns=recent_purchases_columns,
            rows=[],
            row_key="purchase_number",
            pagination=10,
        ).classes("w-full")

    with ui.card().classes("w-full q-pa-md"):
        ui.label("Low Stock Products").classes("text-h6 q-mb-sm")
        low_stock_table = ui.table(
            columns=low_stock_columns,
            rows=[],
            row_key="product_name",
            pagination=10,
        ).classes("w-full")

    try:
        data = load_dashboard_data()
        cards = data["cards"]
        total_products_label.text = cards["total_products"]
        inventory_value_label.text = cards["inventory_value"]
        total_quantity_label.text = cards["total_quantity"]
        low_stock_count_label.text = cards["low_stock_count"]
        active_debtors_label.text = cards["active_debtors"]
        outstanding_debt_label.text = cards["outstanding_debt"]

        recent_sales_table.rows = data["recent_sales"]
        recent_purchases_table.rows = data["recent_purchases"]
        low_stock_table.rows = data["low_stock_products"]

        recent_sales_table.update()
        recent_purchases_table.update()
        low_stock_table.update()
    except SQLAlchemyError:
        ui.notify("Failed to load dashboard data.", color="negative")

