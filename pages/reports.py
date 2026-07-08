from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from nicegui import ui

from core.i18n import t
from pages.components import (
    add_table_empty_state,
    data_table_card,
    page_header,
    statistic_card,
    statistic_grid,
    style_status_column,
    surface_card,
)
from pages.inventory import load_filter_options
from pages.layout import with_master_layout
from services import excel_export, pdf_export, reports_service


def _report_type_options() -> dict[str, str]:
    return {
        "sales": t("reports.type.sales"),
        "purchases": t("reports.type.purchases"),
        "inventory": t("reports.type.inventory"),
        "debtors": t("reports.type.debtors"),
        "product_sales": t("reports.type.product_sales"),
        "suppliers": t("reports.type.suppliers"),
        "customers": t("reports.type.customers"),
        "stock_movements": t("reports.type.stock_movements"),
    }


def _date_range_options() -> dict[str, str]:
    return {
        "today": t("reports.range.today"),
        "yesterday": t("reports.range.yesterday"),
        "last_7_days": t("reports.range.last_7_days"),
        "this_month": t("reports.range.this_month"),
        "this_year": t("reports.range.this_year"),
        "custom": t("reports.range.custom"),
    }


def _resolve_report_dates(
    date_range: str,
    date_from: str,
    date_to: str,
) -> tuple[str | None, str | None]:
    today = date.today()
    if date_range == "today":
        return today.isoformat(), today.isoformat()
    if date_range == "yesterday":
        yesterday = today - timedelta(days=1)
        return yesterday.isoformat(), yesterday.isoformat()
    if date_range == "last_7_days":
        return (today - timedelta(days=6)).isoformat(), today.isoformat()
    if date_range == "this_month":
        return today.replace(day=1).isoformat(), today.isoformat()
    if date_range == "this_year":
        return today.replace(month=1, day=1).isoformat(), today.isoformat()
    if date_range == "custom":
        return date_from or None, date_to or None
    return None, None


def _sales_report_columns() -> list[dict[str, str]]:
    return [
        {
            "name": "sale_number",
            "label": t("reports.sales.table.sale_number"),
            "field": "sale_number",
            "align": "left",
        },
        {"name": "date", "label": t("reports.sales.table.date"), "field": "date", "align": "left"},
        {
            "name": "customer",
            "label": t("reports.sales.table.customer"),
            "field": "customer",
            "align": "left",
        },
        {
            "name": "items_count",
            "label": t("reports.sales.table.items_count"),
            "field": "items_count",
            "align": "right",
        },
        {
            "name": "total_amount",
            "label": t("reports.sales.table.total_amount"),
            "field": "total_amount",
            "align": "right",
        },
        {
            "name": "paid_amount",
            "label": t("reports.sales.table.paid_amount"),
            "field": "paid_amount",
            "align": "right",
        },
        {
            "name": "remaining_amount",
            "label": t("reports.sales.table.remaining_amount"),
            "field": "remaining_amount",
            "align": "right",
        },
        {
            "name": "payment_type",
            "label": t("reports.sales.table.payment_type"),
            "field": "payment_type",
            "align": "left",
        },
        {
            "name": "status",
            "label": t("reports.sales.table.status"),
            "field": "status",
            "align": "center",
        },
    ]


def _inventory_report_columns() -> list[dict[str, str]]:
    return [
        {
            "name": "product",
            "label": t("reports.inventory.table.product"),
            "field": "product",
            "align": "left",
        },
        {
            "name": "category",
            "label": t("reports.inventory.table.category"),
            "field": "category",
            "align": "left",
        },
        {"name": "size", "label": t("reports.inventory.table.size"), "field": "size", "align": "left"},
        {
            "name": "pressure",
            "label": t("reports.inventory.table.pressure"),
            "field": "pressure",
            "align": "left",
        },
        {
            "name": "quantity",
            "label": t("reports.inventory.table.quantity"),
            "field": "quantity",
            "align": "right",
        },
        {
            "name": "unit_price",
            "label": t("reports.inventory.table.unit_price"),
            "field": "unit_price",
            "align": "right",
        },
        {
            "name": "inventory_value",
            "label": t("reports.inventory.table.inventory_value"),
            "field": "inventory_value",
            "align": "right",
        },
        {
            "name": "status",
            "label": t("reports.inventory.table.status"),
            "field": "status",
            "align": "center",
        },
    ]


def _purchase_report_columns() -> list[dict[str, str]]:
    return [
        {
            "name": "supplier",
            "label": t("reports.purchases.table.supplier"),
            "field": "supplier",
            "align": "left",
        },
        {
            "name": "purchase_number",
            "label": t("reports.purchases.table.purchase_number"),
            "field": "purchase_number",
            "align": "left",
        },
        {"name": "date", "label": t("reports.purchases.table.date"), "field": "date", "align": "left"},
        {"name": "total", "label": t("reports.purchases.table.total"), "field": "total", "align": "right"},
        {"name": "paid", "label": t("reports.purchases.table.paid"), "field": "paid", "align": "right"},
        {
            "name": "remaining",
            "label": t("reports.purchases.table.remaining"),
            "field": "remaining",
            "align": "right",
        },
        {
            "name": "status",
            "label": t("reports.purchases.table.status"),
            "field": "status",
            "align": "center",
        },
    ]


def _debtors_report_columns() -> list[dict[str, str]]:
    return [
        {
            "name": "customer",
            "label": t("reports.debtors.table.customer"),
            "field": "customer",
            "align": "left",
        },
        {
            "name": "sale_number",
            "label": t("reports.debtors.table.sale_number"),
            "field": "sale_number",
            "align": "left",
        },
        {"name": "debt", "label": t("reports.debtors.table.debt"), "field": "debt", "align": "right"},
        {"name": "paid", "label": t("reports.debtors.table.paid"), "field": "paid", "align": "right"},
        {
            "name": "remaining",
            "label": t("reports.debtors.table.remaining"),
            "field": "remaining",
            "align": "right",
        },
        {
            "name": "status",
            "label": t("reports.debtors.table.status"),
            "field": "status",
            "align": "center",
        },
    ]


def _product_sales_report_columns() -> list[dict[str, str]]:
    return [
        {
            "name": "product",
            "label": t("reports.product_sales.table.product"),
            "field": "product",
            "align": "left",
            "sortable": True,
        },
        {
            "name": "quantity_sold",
            "label": t("reports.product_sales.table.quantity_sold"),
            "field": "quantity_sold",
            "align": "right",
            "sortable": True,
        },
        {
            "name": "revenue",
            "label": t("reports.product_sales.table.revenue"),
            "field": "revenue",
            "align": "right",
            "sortable": True,
        },
        {
            "name": "sales_count",
            "label": t("reports.product_sales.table.sales_count"),
            "field": "sales_count",
            "align": "right",
            "sortable": True,
        },
    ]


def _supplier_report_columns() -> list[dict[str, str]]:
    return [
        {
            "name": "supplier",
            "label": t("reports.suppliers.table.supplier"),
            "field": "supplier",
            "align": "left",
            "sortable": True,
        },
        {
            "name": "purchases_count",
            "label": t("reports.suppliers.table.purchases_count"),
            "field": "purchases_count",
            "align": "right",
            "sortable": True,
        },
        {
            "name": "total_spent",
            "label": t("reports.suppliers.table.total_spent"),
            "field": "total_spent",
            "align": "right",
            "sortable": True,
        },
        {
            "name": "paid",
            "label": t("reports.suppliers.table.paid"),
            "field": "paid",
            "align": "right",
            "sortable": True,
        },
        {
            "name": "remaining",
            "label": t("reports.suppliers.table.remaining"),
            "field": "remaining",
            "align": "right",
            "sortable": True,
        },
    ]


def _customer_report_columns() -> list[dict[str, str]]:
    return [
        {
            "name": "customer",
            "label": t("reports.customers.table.customer"),
            "field": "customer",
            "align": "left",
            "sortable": True,
        },
        {
            "name": "sales_count",
            "label": t("reports.customers.table.sales_count"),
            "field": "sales_count",
            "align": "right",
            "sortable": True,
        },
        {
            "name": "total_revenue",
            "label": t("reports.customers.table.total_revenue"),
            "field": "total_revenue",
            "align": "right",
            "sortable": True,
        },
        {
            "name": "paid",
            "label": t("reports.customers.table.paid"),
            "field": "paid",
            "align": "right",
            "sortable": True,
        },
        {
            "name": "remaining",
            "label": t("reports.customers.table.remaining"),
            "field": "remaining",
            "align": "right",
            "sortable": True,
        },
    ]


def _stock_movement_report_columns() -> list[dict[str, str]]:
    return [
        {
            "name": "date",
            "label": t("reports.stock_movements.table.date"),
            "field": "date",
            "align": "left",
            "sortable": True,
        },
        {
            "name": "product",
            "label": t("reports.stock_movements.table.product"),
            "field": "product",
            "align": "left",
            "sortable": True,
        },
        {
            "name": "movement_type",
            "label": t("reports.stock_movements.table.movement_type"),
            "field": "movement_type",
            "align": "center",
            "sortable": True,
        },
        {
            "name": "quantity",
            "label": t("reports.stock_movements.table.quantity"),
            "field": "quantity",
            "align": "right",
            "sortable": True,
        },
        {
            "name": "reference_type",
            "label": t("reports.stock_movements.table.reference_type"),
            "field": "reference_type",
            "align": "left",
            "sortable": True,
        },
        {
            "name": "reference_id",
            "label": t("reports.stock_movements.table.reference_id"),
            "field": "reference_id",
            "align": "right",
            "sortable": True,
        },
    ]


@ui.page("/reports")
@with_master_layout(t("reports.title"))
def reports_page() -> None:
    ui.add_css(
        """
        .fc-report-preview {
            width: 100%;
            min-width: 0;
            max-width: 100%;
            box-sizing: border-box;
        }

        .fc-report-preview-content {
            width: 100%;
            min-width: 0;
            max-width: 100%;
            box-sizing: border-box;
        }

        .fc-report-stat-grid {
            width: 100%;
            min-width: 0;
            max-width: 100%;
            grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr));
        }

        .fc-report-preview-table {
            width: 100%;
            min-width: 0;
            max-width: 100%;
            box-sizing: border-box;
            overflow-x: auto;
        }

        .fc-report-preview-table .q-table__container {
            width: 100%;
            min-width: 0;
        }
        """
    )

    page_header(t("reports.title"), t("reports.description"))

    filter_options = load_filter_options()
    selection: dict[str, Any] = {
        "report_type": "sales",
        "date_range": "this_month",
        "date_from": date.today().isoformat(),
        "date_to": date.today().isoformat(),
        "filters": {
            "search": "",
            "category_id": "",
            "size": "",
            "pressure": "",
            "stock_status": "",
        },
    }

    with surface_card().classes("flex flex-col gap-4"):
        with ui.row().classes("w-full gap-3 items-end no-wrap flex-wrap"):
            report_type_select = ui.select(
                options=_report_type_options(),
                label=t("reports.field.report_type"),
                value=selection["report_type"],
            ).classes("min-w-[240px] flex-1")

        date_controls_row = ui.row().classes("w-full gap-3 items-end no-wrap flex-wrap")
        with date_controls_row:
            date_range_select = ui.select(
                options=_date_range_options(),
                label=t("reports.field.date_range"),
                value=selection["date_range"],
            ).classes("min-w-[200px] flex-1")

            custom_dates_row = ui.row().classes("gap-3 items-end no-wrap flex-wrap")
            with custom_dates_row:
                from_date_input = ui.input(
                    t("reports.field.from_date"),
                    value=selection["date_from"],
                ).props("type=date").classes("min-w-[180px]")
                to_date_input = ui.input(
                    t("reports.field.to_date"),
                    value=selection["date_to"],
                ).props("type=date").classes("min-w-[180px]")

        ui.separator()
        ui.label(t("reports.section.filters")).classes("text-subtitle1")
        filters_container = ui.column().classes("w-full gap-2 min-h-[48px]")
        with filters_container:
            inventory_filters_row = ui.row().classes("w-full gap-3 items-end no-wrap flex-wrap")
            with inventory_filters_row:
                search_input = ui.input(
                    label=t("reports.inventory.search.label"),
                    placeholder=t("reports.inventory.search.placeholder"),
                ).classes("min-w-[240px] flex-1").props("clearable")
                category_filter = ui.select(
                    options=filter_options["categories"],
                    label=t("reports.inventory.filter.category"),
                    value="",
                ).classes("min-w-[180px] flex-1")
                size_filter = ui.select(
                    options=filter_options["sizes"],
                    label=t("reports.inventory.filter.size"),
                    value="",
                ).classes("min-w-[140px] flex-1")
                pressure_filter = ui.select(
                    options=filter_options["pressures"],
                    label=t("reports.inventory.filter.pressure"),
                    value="",
                ).classes("min-w-[140px] flex-1")
                stock_status_filter = ui.select(
                    options=filter_options["stock_statuses"],
                    label=t("reports.inventory.filter.stock_status"),
                    value="",
                ).classes("min-w-[180px] flex-1")

        with ui.row().classes("w-full justify-end gap-2"):
            export_excel_button = ui.button(
                t("reports.button.export_excel"),
                on_click=lambda: on_export_excel(),
                icon="table_view",
                color="positive",
            )
            export_excel_button.disable()
            export_pdf_button = ui.button(
                t("reports.button.export_pdf"),
                on_click=lambda: on_export_pdf(),
                icon="picture_as_pdf",
                color="primary",
            )
            export_pdf_button.disable()
            ui.button(
                t("reports.button.generate"),
                on_click=lambda: on_generate(),
                icon="assessment",
                color="primary",
            )

    with surface_card().classes("fc-report-preview flex flex-col gap-4 q-mt-md"):
        ui.label(t("reports.section.preview")).classes("text-h6")

        preview_empty = ui.element("div").classes("fc-empty-state")
        with preview_empty:
            ui.label("📊").classes("fc-empty-icon")
            ui.label(t("reports.empty.no_report")).classes("fc-empty-text")

        preview_content = ui.column().classes("fc-report-preview-content w-full gap-5")
        preview_content.set_visibility(False)

        with preview_content:
            sales_summary = statistic_grid().classes("fc-report-stat-grid")
            with sales_summary:
                stat_total_sales = statistic_card(
                    t("reports.sales.stat.total_sales"),
                    icon="receipt_long",
                )
                stat_total_revenue = statistic_card(
                    t("reports.sales.stat.total_revenue"),
                    value="0.00",
                    icon="payments",
                )
                stat_paid_amount = statistic_card(
                    t("reports.sales.stat.paid_amount"),
                    value="0.00",
                    icon="account_balance_wallet",
                )
                stat_outstanding_debt = statistic_card(
                    t("reports.sales.stat.outstanding_debt"),
                    value="0.00",
                    icon="trending_down",
                )

            inventory_summary = statistic_grid().classes("fc-report-stat-grid")
            inventory_summary.set_visibility(False)
            with inventory_summary:
                stat_total_products = statistic_card(
                    t("reports.inventory.stat.total_products"),
                    icon="inventory_2",
                )
                stat_warehouse_value = statistic_card(
                    t("reports.inventory.stat.warehouse_value"),
                    value="0.00",
                    icon="payments",
                )
                stat_low_stock_count = statistic_card(
                    t("reports.inventory.stat.low_stock_count"),
                    icon="warning",
                )
                stat_out_of_stock_count = statistic_card(
                    t("reports.inventory.stat.out_of_stock_count"),
                    icon="remove_shopping_cart",
                )

            purchase_summary = statistic_grid().classes("fc-report-stat-grid")
            purchase_summary.set_visibility(False)
            with purchase_summary:
                stat_total_purchases = statistic_card(
                    t("reports.purchases.stat.total_purchases"),
                    icon="shopping_cart",
                )
                stat_total_spent = statistic_card(
                    t("reports.purchases.stat.total_spent"),
                    value="0.00",
                    icon="payments",
                )
                stat_outstanding_supplier_debt = statistic_card(
                    t("reports.purchases.stat.outstanding_supplier_debt"),
                    value="0.00",
                    icon="trending_down",
                )

            debtors_summary = statistic_grid().classes("fc-report-stat-grid")
            debtors_summary.set_visibility(False)
            with debtors_summary:
                stat_debtors_outstanding = statistic_card(
                    t("reports.debtors.stat.outstanding_debt"),
                    value="0.00",
                    icon="account_balance",
                )
                stat_debtors_collected = statistic_card(
                    t("reports.debtors.stat.collected"),
                    value="0.00",
                    icon="account_balance_wallet",
                )
                stat_active_debtors = statistic_card(
                    t("reports.debtors.stat.active_debtors"),
                    icon="groups",
                )
                stat_paid_debtors = statistic_card(
                    t("reports.debtors.stat.paid_debtors"),
                    icon="check_circle",
                )

            product_sales_summary = statistic_grid().classes("fc-report-stat-grid")
            product_sales_summary.set_visibility(False)
            with product_sales_summary:
                stat_products_sold = statistic_card(
                    t("reports.product_sales.stat.products_sold"),
                    icon="category",
                )
                stat_product_quantity_sold = statistic_card(
                    t("reports.product_sales.stat.quantity_sold"),
                    icon="shopping_bag",
                )
                stat_product_total_revenue = statistic_card(
                    t("reports.product_sales.stat.total_revenue"),
                    value="0.00",
                    icon="payments",
                )

            suppliers_summary = statistic_grid().classes("fc-report-stat-grid")
            suppliers_summary.set_visibility(False)
            with suppliers_summary:
                stat_total_suppliers = statistic_card(
                    t("reports.suppliers.stat.total_suppliers"),
                    icon="local_shipping",
                )
                stat_supplier_purchases = statistic_card(
                    t("reports.suppliers.stat.total_purchases"),
                    icon="shopping_cart",
                )
                stat_supplier_spent = statistic_card(
                    t("reports.suppliers.stat.total_spent"),
                    value="0.00",
                    icon="payments",
                )
                stat_supplier_outstanding = statistic_card(
                    t("reports.suppliers.stat.outstanding_debt"),
                    value="0.00",
                    icon="trending_down",
                )

            customers_summary = statistic_grid().classes("fc-report-stat-grid")
            customers_summary.set_visibility(False)
            with customers_summary:
                stat_total_customers = statistic_card(
                    t("reports.customers.stat.total_customers"),
                    icon="people",
                )
                stat_customer_sales = statistic_card(
                    t("reports.customers.stat.total_sales"),
                    icon="receipt_long",
                )
                stat_customer_revenue = statistic_card(
                    t("reports.customers.stat.total_revenue"),
                    value="0.00",
                    icon="payments",
                )
                stat_customer_outstanding = statistic_card(
                    t("reports.customers.stat.outstanding_debt"),
                    value="0.00",
                    icon="trending_down",
                )

            stock_movements_summary = statistic_grid().classes("fc-report-stat-grid")
            stock_movements_summary.set_visibility(False)
            with stock_movements_summary:
                stat_total_movements = statistic_card(
                    t("reports.stock_movements.stat.total_movements"),
                    icon="swap_vert",
                )
                stat_inbound_quantity = statistic_card(
                    t("reports.stock_movements.stat.inbound_quantity"),
                    icon="arrow_downward",
                )
                stat_outbound_quantity = statistic_card(
                    t("reports.stock_movements.stat.outbound_quantity"),
                    icon="arrow_upward",
                )
                stat_net_quantity = statistic_card(
                    t("reports.stock_movements.stat.net_quantity"),
                    icon="balance",
                )

            with data_table_card().classes("fc-report-preview-table"):
                preview_table = ui.table(
                    columns=_sales_report_columns(),
                    rows=[],
                    row_key="sale_number",
                    pagination=15,
                ).classes("w-full")

        style_status_column(preview_table, "status")
        add_table_empty_state(preview_table, t("reports.empty.no_report"), icon="📊")

        preview_state: dict[str, Any] = {
            "report_type": None,
            "report_title": "",
            "columns": [],
            "rows": [],
            "date_from": None,
            "date_to": None,
        }

        def set_preview_state(
            *,
            report_type: str,
            report_title: str,
            columns: list[dict[str, Any]],
            rows: list[dict[str, Any]],
            date_from: str | None = None,
            date_to: str | None = None,
        ) -> None:
            preview_state["report_type"] = report_type
            preview_state["report_title"] = report_title
            preview_state["columns"] = columns
            preview_state["rows"] = rows
            preview_state["date_from"] = date_from
            preview_state["date_to"] = date_to
            export_excel_button.enable()
            export_pdf_button.enable()

        def clear_preview_state() -> None:
            preview_state["report_type"] = None
            preview_state["report_title"] = ""
            preview_state["columns"] = []
            preview_state["rows"] = []
            preview_state["date_from"] = None
            preview_state["date_to"] = None
            export_excel_button.disable()
            export_pdf_button.disable()

        def sync_custom_dates_visibility() -> None:
            custom_dates_row.set_visibility(selection["date_range"] == "custom")

        def sync_report_controls() -> None:
            report_type = str(selection["report_type"])
            is_inventory = report_type == "inventory"
            date_controls_row.set_visibility(not is_inventory)
            inventory_filters_row.set_visibility(is_inventory)

        def on_report_type_change(e: Any) -> None:
            selection["report_type"] = e.value or "sales"
            sync_report_controls()

        def on_date_range_change(e: Any) -> None:
            selection["date_range"] = e.value or "this_month"
            sync_custom_dates_visibility()

        report_type_select.on_value_change(on_report_type_change)
        date_range_select.on_value_change(on_date_range_change)
        sync_custom_dates_visibility()
        sync_report_controls()

        def hide_all_summaries() -> None:
            sales_summary.set_visibility(False)
            inventory_summary.set_visibility(False)
            purchase_summary.set_visibility(False)
            debtors_summary.set_visibility(False)
            product_sales_summary.set_visibility(False)
            suppliers_summary.set_visibility(False)
            customers_summary.set_visibility(False)
            stock_movements_summary.set_visibility(False)

        def show_sales_preview(rows: list[dict[str, Any]]) -> None:
            columns = _sales_report_columns()
            preview_table.columns = columns
            preview_table._props["row-key"] = "sale_number"
            preview_table.rows = rows
            preview_table.update()
            summary = reports_service.summarize_sales_report(rows)
            stat_total_sales.text = summary["total_sales"]
            stat_total_revenue.text = summary["total_revenue"]
            stat_paid_amount.text = summary["paid_amount"]
            stat_outstanding_debt.text = summary["outstanding_debt"]
            hide_all_summaries()
            sales_summary.set_visibility(True)
            preview_empty.set_visibility(False)
            preview_content.set_visibility(True)
            set_preview_state(
                report_type="sales",
                report_title=t("reports.type.sales"),
                columns=columns,
                rows=rows,
                date_from=selection.get("resolved_date_from"),
                date_to=selection.get("resolved_date_to"),
            )

        def show_inventory_preview(rows: list[dict[str, Any]]) -> None:
            columns = _inventory_report_columns()
            preview_table.columns = columns
            preview_table._props["row-key"] = "product_id"
            preview_table.rows = rows
            preview_table.update()
            summary = reports_service.summarize_inventory_report(rows)
            stat_total_products.text = summary["total_products"]
            stat_warehouse_value.text = summary["warehouse_value"]
            stat_low_stock_count.text = summary["low_stock_count"]
            stat_out_of_stock_count.text = summary["out_of_stock_count"]
            hide_all_summaries()
            inventory_summary.set_visibility(True)
            preview_empty.set_visibility(False)
            preview_content.set_visibility(True)
            set_preview_state(
                report_type="inventory",
                report_title=t("reports.type.inventory"),
                columns=columns,
                rows=rows,
            )

        def show_purchase_preview(rows: list[dict[str, Any]]) -> None:
            columns = _purchase_report_columns()
            preview_table.columns = columns
            preview_table._props["row-key"] = "purchase_number"
            preview_table.rows = rows
            preview_table.update()
            summary = reports_service.summarize_purchase_report(rows)
            stat_total_purchases.text = summary["total_purchases"]
            stat_total_spent.text = summary["total_spent"]
            stat_outstanding_supplier_debt.text = summary["outstanding_supplier_debt"]
            hide_all_summaries()
            purchase_summary.set_visibility(True)
            preview_empty.set_visibility(False)
            preview_content.set_visibility(True)
            set_preview_state(
                report_type="purchases",
                report_title=t("reports.type.purchases"),
                columns=columns,
                rows=rows,
                date_from=selection.get("resolved_date_from"),
                date_to=selection.get("resolved_date_to"),
            )

        def show_debtors_preview(rows: list[dict[str, Any]]) -> None:
            columns = _debtors_report_columns()
            preview_table.columns = columns
            preview_table._props["row-key"] = "debtor_id"
            preview_table.rows = rows
            preview_table.update()
            summary = reports_service.summarize_debtors_report(rows)
            stat_debtors_outstanding.text = summary["outstanding_debt"]
            stat_debtors_collected.text = summary["collected"]
            stat_active_debtors.text = summary["active_debtors"]
            stat_paid_debtors.text = summary["paid_debtors"]
            hide_all_summaries()
            debtors_summary.set_visibility(True)
            preview_empty.set_visibility(False)
            preview_content.set_visibility(True)
            set_preview_state(
                report_type="debtors",
                report_title=t("reports.type.debtors"),
                columns=columns,
                rows=rows,
                date_from=selection.get("resolved_date_from"),
                date_to=selection.get("resolved_date_to"),
            )

        def show_product_sales_preview(rows: list[dict[str, Any]]) -> None:
            columns = _product_sales_report_columns()
            preview_table.columns = columns
            preview_table._props["row-key"] = "product_id"
            preview_table.rows = rows
            preview_table.update()
            summary = reports_service.summarize_product_sales_report(rows)
            stat_products_sold.text = summary["products_sold"]
            stat_product_quantity_sold.text = summary["quantity_sold"]
            stat_product_total_revenue.text = summary["total_revenue"]
            hide_all_summaries()
            product_sales_summary.set_visibility(True)
            preview_empty.set_visibility(False)
            preview_content.set_visibility(True)
            set_preview_state(
                report_type="product_sales",
                report_title=t("reports.type.product_sales"),
                columns=columns,
                rows=rows,
                date_from=selection.get("resolved_date_from"),
                date_to=selection.get("resolved_date_to"),
            )

        def show_supplier_preview(rows: list[dict[str, Any]]) -> None:
            columns = _supplier_report_columns()
            preview_table.columns = columns
            preview_table._props["row-key"] = "supplier_id"
            preview_table.rows = rows
            preview_table.update()
            summary = reports_service.summarize_supplier_report(rows)
            stat_total_suppliers.text = summary["total_suppliers"]
            stat_supplier_purchases.text = summary["total_purchases"]
            stat_supplier_spent.text = summary["total_spent"]
            stat_supplier_outstanding.text = summary["outstanding_debt"]
            hide_all_summaries()
            suppliers_summary.set_visibility(True)
            preview_empty.set_visibility(False)
            preview_content.set_visibility(True)
            set_preview_state(
                report_type="suppliers",
                report_title=t("reports.type.suppliers"),
                columns=columns,
                rows=rows,
                date_from=selection.get("resolved_date_from"),
                date_to=selection.get("resolved_date_to"),
            )

        def show_customer_preview(rows: list[dict[str, Any]]) -> None:
            columns = _customer_report_columns()
            preview_table.columns = columns
            preview_table._props["row-key"] = "customer_id"
            preview_table.rows = rows
            preview_table.update()
            summary = reports_service.summarize_customer_report(rows)
            stat_total_customers.text = summary["total_customers"]
            stat_customer_sales.text = summary["total_sales"]
            stat_customer_revenue.text = summary["total_revenue"]
            stat_customer_outstanding.text = summary["outstanding_debt"]
            hide_all_summaries()
            customers_summary.set_visibility(True)
            preview_empty.set_visibility(False)
            preview_content.set_visibility(True)
            set_preview_state(
                report_type="customers",
                report_title=t("reports.type.customers"),
                columns=columns,
                rows=rows,
                date_from=selection.get("resolved_date_from"),
                date_to=selection.get("resolved_date_to"),
            )

        def show_stock_movement_preview(rows: list[dict[str, Any]]) -> None:
            columns = _stock_movement_report_columns()
            preview_table.columns = columns
            preview_table._props["row-key"] = "movement_id"
            preview_table.rows = rows
            preview_table.update()
            summary = reports_service.summarize_stock_movement_report(rows)
            stat_total_movements.text = summary["total_movements"]
            stat_inbound_quantity.text = summary["inbound_quantity"]
            stat_outbound_quantity.text = summary["outbound_quantity"]
            stat_net_quantity.text = summary["net_quantity"]
            hide_all_summaries()
            stock_movements_summary.set_visibility(True)
            preview_empty.set_visibility(False)
            preview_content.set_visibility(True)
            set_preview_state(
                report_type="stock_movements",
                report_title=t("reports.type.stock_movements"),
                columns=columns,
                rows=rows,
                date_from=selection.get("resolved_date_from"),
                date_to=selection.get("resolved_date_to"),
            )

        def show_empty_preview() -> None:
            preview_table.rows = []
            preview_table.update()
            preview_empty.set_visibility(True)
            preview_content.set_visibility(False)
            clear_preview_state()

        preview_handlers: dict[str, Any] = {
            "sales": show_sales_preview,
            "purchases": show_purchase_preview,
            "inventory": show_inventory_preview,
            "debtors": show_debtors_preview,
            "product_sales": show_product_sales_preview,
            "suppliers": show_supplier_preview,
            "customers": show_customer_preview,
            "stock_movements": show_stock_movement_preview,
        }

        def on_export_excel() -> None:
            if not preview_state.get("report_type") or not preview_state.get("columns"):
                ui.notify(t("reports.notify.export_empty"), color="warning")
                return
            try:
                content = excel_export.build_report_workbook(
                    report_title=str(preview_state["report_title"]),
                    columns=list(preview_state["columns"]),
                    rows=list(preview_state["rows"]),
                    date_from=preview_state.get("date_from"),
                    date_to=preview_state.get("date_to"),
                )
                report_type = str(preview_state["report_type"])
                excel_export.save_report_workbook(content, report_type=report_type)
                filename = (
                    f"{report_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                )
                ui.download.content(content, filename)
                ui.notify(t("reports.notify.export_ready"), color="positive")
            except Exception:
                ui.notify(t("reports.notify.export_failed"), color="negative")

        def on_export_pdf() -> None:
            if not preview_state.get("report_type") or not preview_state.get("columns"):
                ui.notify(t("reports.notify.export_empty"), color="warning")
                return
            try:
                content = pdf_export.build_report_pdf(
                    report_title=str(preview_state["report_title"]),
                    columns=list(preview_state["columns"]),
                    rows=list(preview_state["rows"]),
                    date_from=preview_state.get("date_from"),
                    date_to=preview_state.get("date_to"),
                )
                report_type = str(preview_state["report_type"])
                pdf_export.save_report_pdf(content, report_type=report_type)
                filename = (
                    f"{report_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                )
                ui.download.content(content, filename, media_type="application/pdf")
                ui.notify(t("reports.notify.export_pdf_ready"), color="positive")
            except Exception:
                ui.notify(t("reports.notify.export_pdf_failed"), color="negative")

        def on_generate() -> None:
            selection["date_from"] = str(from_date_input.value or "")
            selection["date_to"] = str(to_date_input.value or "")
            report_type = str(selection["report_type"])
            handler = preview_handlers.get(report_type)
            if handler is None:
                show_empty_preview()
                ui.notify(t("reports.notify.coming_next"), color="info")
                return

            if report_type == "inventory":
                selection["resolved_date_from"] = None
                selection["resolved_date_to"] = None
                selection["filters"] = {
                    "search": str(search_input.value or ""),
                    "category_id": str(category_filter.value or ""),
                    "size": str(size_filter.value or ""),
                    "pressure": str(pressure_filter.value or ""),
                    "stock_status": str(stock_status_filter.value or ""),
                }
                rows = reports_service.generate_report(
                    report_type=report_type,
                    filters=dict(selection["filters"]),
                )
                handler(rows)
                return

            date_from, date_to = _resolve_report_dates(
                str(selection["date_range"]),
                selection["date_from"],
                selection["date_to"],
            )
            selection["resolved_date_from"] = date_from
            selection["resolved_date_to"] = date_to
            rows = reports_service.generate_report(
                report_type=report_type,
                date_from=date_from,
                date_to=date_to,
                filters=dict(selection["filters"]),
            )
            handler(rows)