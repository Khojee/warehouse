from __future__ import annotations

from datetime import date
from typing import Any

from nicegui import ui

from core.i18n import t
from pages.components import page_header, surface_card
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


@ui.page("/reports")
@with_master_layout(t("reports.title"))
def reports_page() -> None:
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
            report_type_select = ui.select(
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
            is_custom = selection["date_range"] == "custom"
            custom_dates_row.set_visibility(is_custom)

        def on_date_range_change(e: Any) -> None:
            selection["date_range"] = e.value or "this_month"
            sync_custom_dates_visibility()

        date_range_select.on_value_change(on_date_range_change)
        sync_custom_dates_visibility()

        ui.separator()
        ui.label(t("reports.section.filters")).classes("text-subtitle1")
        # Dynamic filters will be rendered here based on report type.
        filters_container = ui.column().classes("w-full gap-2 min-h-[48px]")
        with filters_container:
            pass

        def on_generate() -> None:
            selection["date_from"] = str(from_date_input.value or "")
            selection["date_to"] = str(to_date_input.value or "")
            reports_service.generate_report(
                report_type=str(selection["report_type"]),
                date_from=selection["date_from"] if selection["date_range"] == "custom" else None,
                date_to=selection["date_to"] if selection["date_range"] == "custom" else None,
                filters=dict(selection["filters"]),
            )
            ui.notify(t("reports.notify.coming_next"), color="info")

        with ui.row().classes("w-full justify-end"):
            ui.button(
                t("reports.button.generate"),
                on_click=on_generate,
                icon="assessment",
                color="primary",
            )

    with surface_card().classes("flex flex-col gap-2 q-mt-md").style("min-height: 360px;"):
        ui.label(t("reports.section.preview")).classes("text-h6")
        with ui.element("div").classes("fc-empty-state").style("flex: 1 1 auto;"):
            ui.label("📊").classes("fc-empty-icon")
            ui.label(t("reports.empty.no_report")).classes("fc-empty-text")
