from __future__ import annotations

from decimal import Decimal
from typing import Any

from nicegui import ui
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from core.i18n import payment_status_label, t
from database import SessionLocal
from models import Debtor, Inventory, Product, Purchase, Sale
from pages.components import (
    add_table_empty_state,
    data_table_card,
    page_header,
    statistic_card,
    statistic_grid,
    style_status_column,
    summary_item,
    summary_list,
    surface_card,
)
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
                "customer": sale.customer.full_name if sale.customer else t("common.placeholder.dash"),
                "total_amount": f"{sale.total_amount:.2f}",
                "status": payment_status_label(sale.payment_status or ""),
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
                "supplier": purchase.supplier.company_name if purchase.supplier else t("common.placeholder.dash"),
                "total_amount": f"{purchase.total_amount:.2f}",
                "status": payment_status_label(purchase.payment_status or ""),
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
@with_master_layout(t("dashboard.title"))
def dashboard_page() -> None:
    page_header(t("dashboard.title"), t("dashboard.description"))

    with statistic_grid():
        total_products_label = statistic_card(t("dashboard.stat.total_products"), icon="category")
        inventory_value_label = statistic_card(t("dashboard.stat.inventory_value"), value="0.00", icon="account_balance_wallet")
        total_quantity_label = statistic_card(t("dashboard.stat.total_quantity_in_stock"), icon="inventory_2")
        low_stock_count_label = statistic_card(t("dashboard.stat.low_stock_count"), icon="report_problem")
        active_debtors_label = statistic_card(t("dashboard.stat.active_debtors"), icon="payments")
        outstanding_debt_label = statistic_card(t("dashboard.stat.outstanding_debt"), value="0.00", icon="trending_down")

    recent_sales_columns = [
        {"name": "sale_number", "label": t("dashboard.table.sale_number"), "field": "sale_number", "align": "left"},
        {"name": "date", "label": t("common.table.date"), "field": "date", "align": "left"},
        {"name": "customer", "label": t("dashboard.table.customer"), "field": "customer", "align": "left"},
        {"name": "total_amount", "label": t("dashboard.table.total_amount"), "field": "total_amount", "align": "right"},
        {"name": "status", "label": t("common.table.status"), "field": "status", "align": "center"},
    ]
    recent_purchases_columns = [
        {"name": "purchase_number", "label": t("dashboard.table.purchase_number"), "field": "purchase_number", "align": "left"},
        {"name": "date", "label": t("common.table.date"), "field": "date", "align": "left"},
        {"name": "supplier", "label": t("dashboard.table.supplier"), "field": "supplier", "align": "left"},
        {"name": "total_amount", "label": t("dashboard.table.total_amount"), "field": "total_amount", "align": "right"},
        {"name": "status", "label": t("common.table.status"), "field": "status", "align": "center"},
    ]
    low_stock_columns = [
        {"name": "product_name", "label": t("dashboard.table.product"), "field": "product_name", "align": "left"},
        {"name": "quantity", "label": t("common.table.quantity"), "field": "quantity", "align": "right"},
        {"name": "min_stock", "label": t("dashboard.table.min_stock"), "field": "min_stock", "align": "right"},
        {"name": "unit", "label": t("dashboard.table.unit"), "field": "unit", "align": "left"},
    ]

    with ui.element("div").classes("fc-dash-main w-full"):
        with data_table_card(t("dashboard.card.recent_sales"), icon="point_of_sale"):
            recent_sales_table = ui.table(
                columns=recent_sales_columns,
                rows=[],
                row_key="sale_number",
                pagination=0,
            ).props("hide-pagination").classes("w-full")

        with surface_card().classes("fc-dash-insights"):
            with ui.element("div").classes("fc-table-card-header"):
                ui.icon("insights")
                ui.label(t("dashboard.card.quick_insights")).classes("fc-table-card-title")
            with summary_list():
                insight_low_stock = summary_item(t("dashboard.insight.low_stock_products"), icon="report_problem")
                insight_active_debtors = summary_item(t("dashboard.stat.active_debtors"), icon="payments")
                insight_outstanding_debt = summary_item(t("dashboard.stat.outstanding_debt"), value="0.00", icon="trending_down")
                insight_recent_purchases = summary_item(t("dashboard.insight.recent_purchases"), icon="shopping_cart")

    with data_table_card(t("dashboard.card.recent_purchases"), icon="shopping_cart"):
        recent_purchases_table = ui.table(
            columns=recent_purchases_columns,
            rows=[],
            row_key="purchase_number",
            pagination=0,
        ).props("hide-pagination").classes("w-full")

    with data_table_card(t("dashboard.card.low_stock_products"), icon="report_problem"):
        low_stock_table = ui.table(
            columns=low_stock_columns,
            rows=[],
            row_key="product_name",
            pagination=10,
        ).classes("w-full")

    style_status_column(recent_sales_table, "status")
    style_status_column(recent_purchases_table, "status")
    add_table_empty_state(recent_sales_table, t("dashboard.empty.no_sales"), icon="🧾")
    add_table_empty_state(recent_purchases_table, t("dashboard.empty.no_purchases"), icon="📦")
    add_table_empty_state(low_stock_table, t("dashboard.empty.no_low_stock"), icon="✅")

    ui.add_css(
        """
        .fc-dash-main {
            display: grid;
            grid-template-columns: 1fr;
            gap: 20px;
            align-items: start;
        }
        @media (min-width: 1024px) {
            .fc-dash-main { grid-template-columns: 2fr 1fr; }
        }
        """
    )

    try:
        data = load_dashboard_data()
        cards = data["cards"]
        total_products_label.text = cards["total_products"]
        inventory_value_label.text = cards["inventory_value"]
        total_quantity_label.text = cards["total_quantity"]
        low_stock_count_label.text = cards["low_stock_count"]
        active_debtors_label.text = cards["active_debtors"]
        outstanding_debt_label.text = cards["outstanding_debt"]

        recent_sales_table.rows = data["recent_sales"][:5]
        recent_purchases_table.rows = data["recent_purchases"][:5]
        low_stock_table.rows = data["low_stock_products"]

        insight_low_stock.text = cards["low_stock_count"]
        insight_active_debtors.text = cards["active_debtors"]
        insight_outstanding_debt.text = cards["outstanding_debt"]
        insight_recent_purchases.text = str(len(data["recent_purchases"]))

        recent_sales_table.update()
        recent_purchases_table.update()
        low_stock_table.update()
    except SQLAlchemyError:
        ui.notify(t("dashboard.error.load_failed"), color="negative")
