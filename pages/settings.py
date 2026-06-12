from __future__ import annotations

import time
from typing import Any

from nicegui import ui
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from core.i18n import t
from database import SessionLocal
from models import Setting
from pages.components import page_header, surface_card
from pages.layout import with_master_layout
from services import image_service


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
        raise ValueError(t("settings.error.threshold_integer")) from exc
    if parsed < 0:
        raise ValueError(t("settings.error.threshold_negative"))
    return str(parsed)


@ui.page("/settings")
@with_master_layout(t("settings.title"))
def settings_page() -> None:
    page_header(t("settings.title"), t("settings.description"))

    with surface_card().classes("flex flex-col gap-3"):
        ui.label(t("settings.section.company")).classes("text-h6 q-mb-sm")
        with ui.row().classes("w-full gap-2"):
            company_name_input = ui.input(t("settings.field.company_name")).classes("col")
            company_phone_input = ui.input(t("settings.field.phone")).classes("col")
        with ui.row().classes("w-full gap-2"):
            company_telegram_input = ui.input(t("settings.field.telegram")).classes("col")
            currency_input = ui.input(t("settings.field.currency")).classes("col")
        with ui.row().classes("w-full gap-2"):
            logo_path_input = ui.input(t("settings.field.logo_path")).classes("col")
            low_stock_threshold_input = ui.number(
                t("settings.field.default_low_stock_threshold"),
                value=0,
                min=0,
                precision=0,
            ).classes("col")
        company_address_input = ui.textarea(t("settings.field.company_address")).classes("w-full")

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
                    ui.notify(t("settings.notify.load_failed"), color="negative")

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
                    ui.notify(t("settings.notify.saved"), color="positive")
                except ValueError as exc:
                    ui.notify(str(exc), color="warning")
                except SQLAlchemyError:
                    ui.notify(t("settings.notify.save_failed"), color="negative")

            ui.button(t("common.button.reload"), on_click=reload_settings, color="grey-6")
            ui.button(t("common.button.save_settings"), on_click=save_settings, color="primary")

    with surface_card().classes("flex flex-col gap-3"):
        ui.label(t("settings.section.company_logo")).classes("text-h6 q-mb-sm")
        with ui.row().classes("w-full items-center gap-6 no-wrap"):
            preview_box = (
                ui.element("div")
                .classes("flex items-center justify-center")
                .style(
                    "width:120px;height:120px;border-radius:16px;"
                    "background:#F8FAFC;border:1px dashed rgba(15,23,42,.15);"
                    "flex-shrink:0;overflow:hidden;"
                )
            )

            def render_logo_preview() -> None:
                preview_box.clear()
                with preview_box:
                    logo_path = image_service.get_logo_path()
                    if logo_path:
                        ui.image(f"/{logo_path}?v={int(time.time())}").props(
                            "fit=contain no-spinner"
                        ).style("width:112px;height:112px;")
                    else:
                        with ui.column().classes("items-center gap-1"):
                            ui.icon("image").classes("text-grey-5").style("font-size:40px")
                            ui.label(t("settings.logo.no_logo")).classes("text-caption text-grey-6")

            with ui.column().classes("flex-1 min-w-0 gap-1"):
                ui.label(t("settings.logo.upload_hint")).classes(
                    "text-caption text-grey-7"
                )

                async def handle_logo_upload(e: Any) -> None:
                    ext = image_service.extension_of(e.file.name)
                    if ext is None:
                        ui.notify(
                            t("settings.logo.invalid_format"),
                            color="warning",
                        )
                        logo_upload.reset()
                        return
                    data = await e.file.read()
                    try:
                        relative_path = image_service.save_company_logo(data, ext)
                    except (OSError, SQLAlchemyError):
                        ui.notify(t("settings.notify.logo_save_failed"), color="negative")
                        return
                    logo_path_input.value = relative_path
                    logo_path_input.update()
                    logo_upload.reset()
                    render_logo_preview()
                    ui.notify(t("settings.notify.logo_updated"), color="positive")

                logo_upload = (
                    ui.upload(
                        label=t("common.button.upload_logo"),
                        auto_upload=True,
                        max_file_size=10 * 1024 * 1024,
                        on_upload=handle_logo_upload,
                    )
                    .props('accept=".png,.jpg,.jpeg,.webp" flat bordered')
                    .classes("w-full max-w-md")
                )

        render_logo_preview()

    reload_settings()
