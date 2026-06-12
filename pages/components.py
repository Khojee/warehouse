"""FlowCore reusable UI component system.

Visual components only -- no business logic. Every component injects the
shared component stylesheet once per client.
"""

from __future__ import annotations

from typing import Any

from nicegui import ui

from core.i18n import badge_danger_values, badge_success_values, badge_warning_values, t


_COMPONENTS_CSS = """
/* ============ FlowCore component system ============ */

/* ---------- panels / surfaces ---------- */
.fc-panel {
    background: var(--fc-surface);
    border-radius: 20px;
    padding: 20px;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04), 0 8px 24px rgba(15, 23, 42, 0.06);
    width: 100%;
}

/* ---------- statistic card ---------- */
.fc-stat-grid {
    display: grid;
    grid-template-columns: 1fr;
    gap: 20px;
    width: 100%;
}

@media (min-width: 640px) {
    .fc-stat-grid { grid-template-columns: repeat(2, 1fr); }
}

@media (min-width: 1024px) {
    .fc-stat-grid { grid-template-columns: repeat(3, 1fr); }
}

@media (min-width: 1600px) {
    .fc-stat-grid { grid-template-columns: repeat(4, 1fr); }
}

.fc-stat-card {
    position: relative;
    background: var(--fc-surface);
    border-radius: 20px;
    padding: 24px;
    min-height: 140px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04), 0 8px 24px rgba(15, 23, 42, 0.06);
    transition: transform 200ms ease, box-shadow 200ms ease;
}

.fc-stat-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 2px 4px rgba(15, 23, 42, 0.05), 0 14px 32px rgba(15, 23, 42, 0.10);
}

.fc-stat-top {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
}

.fc-stat-label {
    color: var(--fc-muted);
    font-size: 13.5px;
    font-weight: 600;
    letter-spacing: 0.01em;
}

.fc-stat-icon {
    color: var(--fc-primary);
    font-size: 24px;
    background: rgba(0, 121, 121, 0.08);
    border-radius: 12px;
    padding: 8px;
}

.fc-stat-value {
    font-size: 36px;
    font-weight: 700;
    line-height: 1.1;
    color: var(--fc-text);
    margin-top: 8px;
}

.fc-stat-trend {
    font-size: 12.5px;
    color: var(--fc-muted);
    margin-top: 6px;
}

/* ---------- data table card ---------- */
.fc-table-card {
    background: var(--fc-surface);
    border-radius: 20px;
    padding: 20px;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04), 0 8px 24px rgba(15, 23, 42, 0.06);
    width: 100%;
    min-width: 0;
}

.fc-table-card-header {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 14px;
}

.fc-table-card-title {
    font-size: 17px;
    font-weight: 700;
    color: var(--fc-text);
}

.fc-table-card-header .q-icon {
    color: var(--fc-primary);
    font-size: 20px;
}

.fc-table-card .q-table__container {
    box-shadow: none;
    border-radius: 12px;
    background: transparent;
}

.fc-table-card .q-table thead tr {
    background: var(--fc-bg);
}

.fc-table-card .q-table thead th {
    position: sticky;
    top: 0;
    z-index: 2;
    background: var(--fc-bg);
    font-weight: 600;
    font-size: 13px;
    color: var(--fc-text);
}

.fc-table-card .q-table thead th:first-child { border-top-left-radius: 12px; }
.fc-table-card .q-table thead th:last-child { border-top-right-radius: 12px; }

.fc-table-card .q-table tbody td {
    height: 52px;
    font-size: 14px;
    color: var(--fc-text);
}

.fc-table-card .q-table tbody tr {
    transition: background-color 200ms ease;
}

.fc-table-card .q-table tbody tr:hover {
    background: rgba(255, 224, 197, 0.28);
}

.fc-table-card .q-table__bottom {
    border-top: 1px solid rgba(15, 23, 42, 0.06);
    padding-top: 10px;
    color: var(--fc-muted);
}

/* ---------- status badge ---------- */
.fc-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    height: 28px;
    padding: 0 12px;
    border-radius: 9999px;
    font-size: 12.5px;
    font-weight: 500;
    white-space: nowrap;
}

.fc-badge-success { background: rgba(34, 197, 94, 0.15); color: #22C55E; }
.fc-badge-warning { background: rgba(245, 158, 11, 0.15); color: #F59E0B; }
.fc-badge-danger { background: rgba(239, 68, 68, 0.15); color: #EF4444; }
.fc-badge-neutral { background: rgba(100, 116, 139, 0.12); color: #64748B; }

/* ---------- page header ---------- */
.fc-page-header {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 16px;
    width: 100%;
    margin-bottom: 4px;
    flex-wrap: wrap;
}

.fc-page-title {
    font-size: 26px;
    font-weight: 800;
    letter-spacing: -0.02em;
    color: var(--fc-text);
    line-height: 1.2;
}

.fc-page-description {
    font-size: 14px;
    color: var(--fc-muted);
    margin-top: 4px;
}

.fc-page-header-actions {
    display: flex;
    align-items: center;
    gap: 10px;
}

/* ---------- search panel ---------- */
.fc-search-panel {
    background: var(--fc-surface);
    border-radius: 16px;
    padding: 20px;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04), 0 8px 24px rgba(15, 23, 42, 0.06);
    width: 100%;
}

.fc-search-panel .q-field {
    font-size: 15px;
}

/* ---------- filter sidebar ---------- */
.fc-filter-sidebar {
    background: var(--fc-surface);
    border-radius: 20px;
    padding: 20px;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04), 0 8px 24px rgba(15, 23, 42, 0.06);
    display: flex;
    flex-direction: column;
    gap: 4px;
    width: 280px;
    min-width: 250px;
    max-width: 300px;
    flex-shrink: 0;
    align-self: flex-start;
}

.fc-filter-title {
    font-size: 15px;
    font-weight: 700;
    color: var(--fc-text);
    margin-bottom: 8px;
}

.fc-filter-sidebar .q-field {
    margin-bottom: 12px;
}

/* ---------- summary list ---------- */
.fc-summary-list {
    display: flex;
    flex-direction: column;
    width: 100%;
}

.fc-summary-item {
    display: flex;
    align-items: center;
    gap: 12px;
    min-height: 56px;
    padding: 8px 4px;
}

.fc-summary-item + .fc-summary-item {
    border-top: 1px solid rgba(15, 23, 42, 0.06);
}

.fc-summary-icon {
    color: var(--fc-primary);
    font-size: 20px;
    background: rgba(0, 121, 121, 0.08);
    border-radius: 10px;
    padding: 7px;
    flex-shrink: 0;
}

.fc-summary-label {
    font-size: 14px;
    font-weight: 500;
    color: var(--fc-muted);
    flex: 1 1 auto;
}

.fc-summary-value {
    font-size: 16px;
    font-weight: 700;
    color: var(--fc-text);
}

/* ---------- empty state ---------- */
.fc-empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 8px;
    width: 100%;
    padding: 48px 16px;
    text-align: center;
}

.fc-empty-icon {
    font-size: 40px;
    line-height: 1;
}

.fc-empty-text {
    font-size: 14.5px;
    color: var(--fc-muted);
    font-weight: 500;
}

/* ---------- buttons ---------- */
.q-btn:not(.q-btn--round):not(.q-btn--dense):not(.q-btn--flat) {
    min-height: 44px;
    border-radius: 14px;
    font-weight: 600;
    letter-spacing: 0.01em;
    text-transform: none;
    box-shadow: 0 2px 8px rgba(15, 23, 42, 0.10);
    transition: background-color 200ms ease, box-shadow 200ms ease, transform 200ms ease;
}

.q-btn.bg-primary:hover {
    background: #24B1B1 !important;
}

/* ---------- forms ---------- */
.q-field--labeled .q-field__native,
.q-field--labeled .q-field__input {
    font-size: 14.5px;
    color: var(--fc-text);
}

.q-field__label {
    color: var(--fc-muted);
}

/* ---------- dialogs ---------- */
.q-dialog .q-card {
    border-radius: 20px;
    padding: 8px;
}
"""


def _ensure_styles() -> None:
    """Inject the component stylesheet once per client/page."""
    client = ui.context.client
    if getattr(client, "_fc_components_css", False):
        return
    client._fc_components_css = True  # type: ignore[attr-defined]
    ui.add_css(_COMPONENTS_CSS)


def _badge_class(value: str) -> str:
    if value in badge_success_values():
        return "fc-badge-success"
    if value in badge_warning_values():
        return "fc-badge-warning"
    if value in badge_danger_values():
        return "fc-badge-danger"
    return "fc-badge-neutral"


# ---------------------------------------------------------------- components

def statistic_card(
    label: str,
    *,
    value: str = "0",
    icon: str | None = None,
    trend: str | None = None,
) -> ui.label:
    """StatisticCard: returns the value label so callers can update its text."""
    _ensure_styles()
    with ui.element("div").classes("fc-stat-card"):
        with ui.element("div").classes("fc-stat-top"):
            ui.label(label).classes("fc-stat-label")
            if icon:
                ui.icon(icon).classes("fc-stat-icon")
        value_label = ui.label(value).classes("fc-stat-value")
        if trend:
            ui.label(trend).classes("fc-stat-trend")
    return value_label


def statistic_grid() -> Any:
    """Responsive grid container for StatisticCards."""
    _ensure_styles()
    return ui.element("div").classes("fc-stat-grid")


def data_table_card(title: str | None = None, *, icon: str | None = None) -> Any:
    """DataTableCard: white rounded card container for tables."""
    _ensure_styles()
    card = ui.element("div").classes("fc-table-card")
    if title:
        with card, ui.element("div").classes("fc-table-card-header"):
            if icon:
                ui.icon(icon)
            ui.label(title).classes("fc-table-card-title")
    return card


def status_badge(value: str) -> Any:
    """StatusBadge: rounded pill colored by status semantics."""
    _ensure_styles()
    return ui.label(value).classes(f"fc-badge {_badge_class(value)}")


def _js_single_quoted_array(values: list[str]) -> str:
    """Serialize *values* as a JS array safe inside HTML double-quoted attributes.

    Python ``str(list)`` may emit double-quoted strings (e.g. ``"To'langan"``) which
    terminate a ``:class="..."`` attribute and break Vue template compilation.
    """
    parts: list[str] = []
    for value in values:
        escaped = value.replace("\\", "\\\\").replace("'", "\\'")
        parts.append(f"'{escaped}'")
    return "[" + ", ".join(parts) + "]"


def style_status_column(table: Any, column: str, field: str | None = None) -> None:
    """Render a table column as StatusBadge pills (client-side class mapping)."""
    field = field or column
    success = _js_single_quoted_array(badge_success_values())
    warning = _js_single_quoted_array(badge_warning_values())
    danger = _js_single_quoted_array(badge_danger_values())
    table.add_slot(
        f"body-cell-{column}",
        f"""
        <q-td :props="props">
          <span :class="'fc-badge ' + (
              {success}.includes(String(props.row.{field})) ? 'fc-badge-success'
            : {warning}.includes(String(props.row.{field})) ? 'fc-badge-warning'
            : {danger}.includes(String(props.row.{field})) ? 'fc-badge-danger'
            : 'fc-badge-neutral')">{{{{ props.row.{field} }}}}</span>
        </q-td>
        """,
    )


def add_table_empty_state(table: Any, message: str, *, icon: str = "📦") -> None:
    """Modern empty state shown when a table has no rows."""
    table.add_slot(
        "no-data",
        f"""
        <div class="fc-empty-state">
          <div class="fc-empty-icon">{icon}</div>
          <div class="fc-empty-text">{message}</div>
        </div>
        """,
    )


def page_header(title: str, description: str | None = None) -> Any:
    """PageHeader: consistent title block; returns the actions container."""
    _ensure_styles()
    with ui.element("div").classes("fc-page-header"):
        with ui.element("div").classes("fc-page-header-text"):
            ui.label(title).classes("fc-page-title")
            if description:
                ui.label(description).classes("fc-page-description")
        actions = ui.element("div").classes("fc-page-header-actions")
    return actions


def search_panel() -> Any:
    """SearchPanel: white rounded card hosting page search controls."""
    _ensure_styles()
    return ui.element("div").classes("fc-search-panel")


def filter_sidebar(title: str | None = None) -> Any:
    """FilterSidebar: white rounded surface hosting filter controls."""
    _ensure_styles()
    sidebar = ui.element("div").classes("fc-filter-sidebar")
    with sidebar:
        ui.label(title if title is not None else t("common.filter.title")).classes(
            "fc-filter-title"
        )
    return sidebar


def surface_card() -> Any:
    """Generic white rounded surface (20px radius, soft shadow)."""
    _ensure_styles()
    return ui.element("div").classes("fc-panel")


def summary_list() -> Any:
    """Clean vertical summary list container (e.g. Quick Insights)."""
    _ensure_styles()
    return ui.element("div").classes("fc-summary-list")


def summary_item(label: str, *, value: str = "0", icon: str | None = None) -> ui.label:
    """Summary list row; returns the value label for later updates."""
    _ensure_styles()
    with ui.element("div").classes("fc-summary-item"):
        if icon:
            ui.icon(icon).classes("fc-summary-icon")
        ui.label(label).classes("fc-summary-label")
        value_label = ui.label(value).classes("fc-summary-value")
    return value_label
