from __future__ import annotations

from typing import Any

from nicegui import ui
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from database import SessionLocal
from models import Setting
from pages.layout import with_master_layout


SETTINGS_KEYS = [
    "company_name",
    "company_address",
    "company_phone",
    "company_telegram",
    "currency",
    "logo_path",
    "default_low_stock_threshold",
]


def load_settings_values() -> dict[str, str]:
    with SessionLocal() as session:
        rows = session.scalars(
            select(Setting).where(Setting.key.in_(SETTINGS_KEYS))
        ).all()
    values = {key: "" for key in SETTINGS_KEYS}
    for row in rows:
        values[row.key] = row.value or ""
    return values


def save_settings_values(values: dict[str, str]) -> None:
    with SessionLocal.begin() as session:
        for key in SETTINGS_KEYS:
            value = str(values.get(key, "")).strip()
            setting = session.get(Setting, key)
            if setting is None:
                session.add(Setting(key=key, value=value))
            else:
                setting.value = value


def parse_low_stock_threshold(value: Any) -> str:
    if value in (None, ""):
        return "0"
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Default Low Stock Threshold must be an integer.") from exc
    if parsed < 0:
        raise ValueError("Default Low Stock Threshold cannot be negative.")
    return str(parsed)


@ui.page("/settings")
@with_master_layout("Settings")
def settings_page() -> None:
    ui.label("Settings").classes("text-h4 q-mb-md")

    with ui.card().classes("w-full q-pa-md"):
        ui.label("Company Settings").classes("text-h6 q-mb-sm")
        with ui.row().classes("w-full gap-2"):
            company_name_input = ui.input("Company Name").classes("col")
            company_phone_input = ui.input("Phone").classes("col")
        with ui.row().classes("w-full gap-2"):
            company_telegram_input = ui.input("Telegram").classes("col")
            currency_input = ui.input("Currency").classes("col")
        with ui.row().classes("w-full gap-2"):
            logo_path_input = ui.input("Logo Path").classes("col")
            low_stock_threshold_input = ui.number(
                "Default Low Stock Threshold",
                value=0,
                min=0,
                precision=0,
            ).classes("col")
        company_address_input = ui.textarea("Company Address").classes("w-full")

        with ui.row().classes("justify-end w-full q-mt-sm"):
            def reload_settings() -> None:
                try:
                    values = load_settings_values()
                    company_name_input.value = values["company_name"]
                    company_address_input.value = values["company_address"]
                    company_phone_input.value = values["company_phone"]
                    company_telegram_input.value = values["company_telegram"]
                    currency_input.value = values["currency"]
                    logo_path_input.value = values["logo_path"]
                    low_stock_threshold_input.value = int(
                        values["default_low_stock_threshold"] or "0"
                    )

                    company_name_input.update()
                    company_address_input.update()
                    company_phone_input.update()
                    company_telegram_input.update()
                    currency_input.update()
                    logo_path_input.update()
                    low_stock_threshold_input.update()
                except ValueError:
                    low_stock_threshold_input.value = 0
                    low_stock_threshold_input.update()
                except SQLAlchemyError:
                    ui.notify("Failed to load settings.", color="negative")

            def save_settings() -> None:
                try:
                    threshold = parse_low_stock_threshold(low_stock_threshold_input.value)
                    save_settings_values(
                        {
                            "company_name": str(company_name_input.value or "").strip(),
                            "company_address": str(company_address_input.value or "").strip(),
                            "company_phone": str(company_phone_input.value or "").strip(),
                            "company_telegram": str(company_telegram_input.value or "").strip(),
                            "currency": str(currency_input.value or "").strip(),
                            "logo_path": str(logo_path_input.value or "").strip(),
                            "default_low_stock_threshold": threshold,
                        }
                    )
                    ui.notify("Settings saved successfully.", color="positive")
                except ValueError as exc:
                    ui.notify(str(exc), color="warning")
                except SQLAlchemyError:
                    ui.notify("Failed to save settings.", color="negative")

            ui.button("Reload", on_click=reload_settings, color="grey-6")
            ui.button("Save Settings", on_click=save_settings, color="primary")

    reload_settings()

