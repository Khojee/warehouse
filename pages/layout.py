from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any

from nicegui import ui


COMPANY_NAME = "Warehouse Management System"

NAV_ITEMS = [
    {"label": "Dashboard", "path": "/dashboard", "icon": "dashboard"},
    {"label": "Inventory", "path": "/inventory", "icon": "inventory_2"},
    {"label": "Products", "path": "/products", "icon": "category"},
    {"label": "Suppliers", "path": "/suppliers", "icon": "groups"},
    {"label": "Purchases", "path": "/purchases", "icon": "shopping_cart"},
    {"label": "Sales", "path": "/sales", "icon": "point_of_sale"},
    {"label": "Debtors", "path": "/debtors", "icon": "payments"},
    {"label": "Settings", "path": "/settings", "icon": "settings"},
]


def _sidebar_link_classes(active: bool) -> str:
    base = "w-full justify-start rounded px-3 py-2 transition-colors"
    if active:
        return f"{base} bg-primary text-white"
    return f"{base} text-grey-9 hover:bg-grey-3"


def with_master_layout(page_title: str) -> Callable[[Callable[..., Any]], Callable[..., None]]:
    def decorator(page_fn: Callable[..., Any]) -> Callable[..., None]:
        @wraps(page_fn)
        def wrapped(*args: Any, **kwargs: Any) -> None:
            current_path = str(ui.context.client.request.url.path)

            with ui.left_drawer(value=True).props("bordered").classes("bg-grey-1"):
                ui.label(COMPANY_NAME).classes("text-subtitle1 text-weight-bold q-pa-sm")
                ui.separator()
                with ui.column().classes("w-full q-gutter-xs q-mt-sm"):
                    for item in NAV_ITEMS:
                        ui.button(
                            item["label"],
                            icon=item["icon"],
                            on_click=lambda path=item["path"]: ui.navigate.to(path),
                        ).props("flat no-caps").classes(
                            _sidebar_link_classes(active=current_path == item["path"])
                        )

            with ui.header(elevated=True).classes("bg-primary text-white"):
                with ui.row().classes("w-full items-center justify-between no-wrap px-4"):
                    with ui.column().classes("q-gutter-none"):
                        ui.label(COMPANY_NAME).classes("text-subtitle2 text-weight-medium")
                        ui.label(page_title).classes("text-h6 text-weight-bold")
                    ui.button("User Menu", icon="account_circle").props("flat")

            with ui.column().classes("w-full q-pa-md"):
                page_fn(*args, **kwargs)

        return wrapped

    return decorator
