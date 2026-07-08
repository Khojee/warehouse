"""Reports service foundation for FlowCore.

No SQL, PDF, or Excel generation yet — only request scaffolding and a
placeholder for future report pipelines.
"""

from __future__ import annotations

from typing import Any


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

DATE_RANGE_PRESETS: tuple[str, ...] = (
    "today",
    "yesterday",
    "last_7_days",
    "this_month",
    "this_year",
    "custom",
)


def generate_report(
    *,
    report_type: str,
    date_range: str,
    date_from: str | None = None,
    date_to: str | None = None,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Placeholder report generator.

    Accepts the UI selections and returns a stub result. Real queries and
    export formats will be added in a later stage.
    """
    return {
        "status": "pending",
        "report_type": report_type,
        "date_range": date_range,
        "date_from": date_from,
        "date_to": date_to,
        "filters": filters or {},
        "rows": [],
        "summary": {},
        "message": "Report generation coming next.",
    }
