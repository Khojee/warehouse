from __future__ import annotations

from datetime import date, timedelta
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
from pages.layout import with_master_layout
from services import reports_service


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

    selection: dict[str, Any] = {
        "report_type": "sales",
        "date_range": "this_month",
        "date_from": date.today().isoformat(),
        "date_to": date.today().isoformat(),
        "filters": {},
    }

    with surface_card().classes("flex flex-col gap-4"):
        with ui.row().classes("w-full gap-3 items-end no-wrap flex-wrap"):
            ui.select(
                options=_report_type_options(),
                label=t("reports.field.report_type"),
                value=selection["report_type"],
                on_change=lambda e: selection.__setitem__("report_type", e.value or "sales"),
            ).classes("min-w-[240px] flex-1")

            date_range_select = ui.select(
                options=_date_range_options(),
                label=t("reports.field.date_range"),
                value=selection["date_range"],
            ).classes("min-w-[200px] flex-1")

        custom_dates_row = ui.row().classes("w-full gap-3 items-end no-wrap flex-wrap")
        with custom_dates_row:
            from_date_input = ui.input(
                t("reports.field.from_date"),
                value=selection["date_from"],
            ).props("type=date").classes("min-w-[180px]")
            to_date_input = ui.input(
                t("reports.field.to_date"),
                value=selection["date_to"],
            ).props("type=date").classes("min-w-[180px]")

        def sync_custom_dates_visibility() -> None:
            custom_dates_row.set_visibility(selection["date_range"] == "custom")

        def on_date_range_change(e: Any) -> None:
            selection["date_range"] = e.value or "this_month"
            sync_custom_dates_visibility()

        date_range_select.on_value_change(on_date_range_change)
        sync_custom_dates_visibility()

        ui.separator()
        ui.label(t("reports.section.filters")).classes("text-subtitle1")
        filters_container = ui.column().classes("w-full gap-2 min-h-[48px]")
        with filters_container:
            pass

        with ui.row().classes("w-full justify-end"):
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
            with statistic_grid().classes("fc-report-stat-grid"):
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

            with data_table_card().classes("fc-report-preview-table"):
                preview_table = ui.table(
                    columns=_sales_report_columns(),
                    rows=[],
                    row_key="sale_number",
                    pagination=15,
                ).classes("w-full")

        style_status_column(preview_table, "status")
        add_table_empty_state(preview_table, t("reports.empty.no_report"), icon="📊")

        def show_sales_preview(rows: list[dict[str, Any]]) -> None:
            preview_table.rows = rows
            preview_table.update()
            summary = reports_service.summarize_sales_report(rows)
            stat_total_sales.text = summary["total_sales"]
            stat_total_revenue.text = summary["total_revenue"]
            stat_paid_amount.text = summary["paid_amount"]
            stat_outstanding_debt.text = summary["outstanding_debt"]
            preview_empty.set_visibility(False)
            preview_content.set_visibility(True)

        def show_empty_preview() -> None:
            preview_table.rows = []
            preview_table.update()
            preview_empty.set_visibility(True)
            preview_content.set_visibility(False)

        def on_generate() -> None:
            selection["date_from"] = str(from_date_input.value or "")
            selection["date_to"] = str(to_date_input.value or "")
            report_type = str(selection["report_type"])

            if report_type != "sales":
                show_empty_preview()
                ui.notify(t("reports.notify.coming_next"), color="info")
                return

            date_from, date_to = _resolve_report_dates(
                str(selection["date_range"]),
                selection["date_from"],
                selection["date_to"],
            )
            rows = reports_service.generate_report(
                report_type=report_type,
                date_from=date_from,
                date_to=date_to,
                filters=dict(selection["filters"]),
            )
            show_sales_preview(rows)
