from __future__ import annotations

from typing import Any

from nicegui import ui
from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError

from core.i18n import t
from database import SessionLocal
from models import Purchase, Supplier
from pages.components import (
    add_table_empty_state,
    data_table_card,
    filter_sidebar,
    page_header,
    search_panel,
)
from pages.layout import with_master_layout


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def load_suppliers(
    *,
    search: str = "",
    has_telegram: str = "",
    has_phone2: str = "",
) -> list[dict[str, Any]]:
    with SessionLocal() as session:
        stmt = select(Supplier).order_by(func.lower(Supplier.company_name).asc())
        if search.strip():
            term = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    Supplier.company_name.ilike(term),
                    Supplier.contact_person.ilike(term),
                    Supplier.phone.ilike(term),
                    Supplier.telegram.ilike(term),
                )
            )

        if has_telegram == "yes":
            stmt = stmt.where(Supplier.telegram.is_not(None)).where(func.trim(Supplier.telegram) != "")
        elif has_telegram == "no":
            stmt = stmt.where(or_(Supplier.telegram.is_(None), func.trim(Supplier.telegram) == ""))

        if has_phone2 == "yes":
            stmt = stmt.where(Supplier.phone2.is_not(None)).where(func.trim(Supplier.phone2) != "")
        elif has_phone2 == "no":
            stmt = stmt.where(or_(Supplier.phone2.is_(None), func.trim(Supplier.phone2) == ""))

        suppliers = session.scalars(stmt).all()

    return [
        {
            "id": supplier.id,
            "company_name": supplier.company_name,
            "contact_person": supplier.contact_person or "",
            "phone": supplier.phone or "",
            "phone2": supplier.phone2 or "",
            "telegram": supplier.telegram or "",
            "address": supplier.address or "",
            "notes": supplier.notes or "",
        }
        for supplier in suppliers
    ]


def create_supplier(data: dict[str, Any]) -> Supplier:
    company_name = str(data.get("company_name", "")).strip()
    phone = str(data.get("phone", "")).strip()
    if not company_name:
        raise ValueError(t("suppliers.error.company_name_required"))
    if not phone:
        raise ValueError(t("suppliers.error.phone_required"))

    with SessionLocal.begin() as session:
        supplier = Supplier(
            company_name=company_name,
            contact_person=_clean_text(data.get("contact_person")),
            phone=phone,
            phone2=_clean_text(data.get("phone2")),
            telegram=_clean_text(data.get("telegram")),
            address=_clean_text(data.get("address")),
            notes=_clean_text(data.get("notes")),
        )
        session.add(supplier)
        session.flush()
        session.refresh(supplier)
        return supplier


def update_supplier(supplier_id: int, data: dict[str, Any]) -> bool:
    company_name = str(data.get("company_name", "")).strip()
    phone = str(data.get("phone", "")).strip()
    if not company_name:
        raise ValueError(t("suppliers.error.company_name_required"))
    if not phone:
        raise ValueError(t("suppliers.error.phone_required"))

    with SessionLocal.begin() as session:
        supplier = session.get(Supplier, supplier_id)
        if supplier is None:
            return False

        supplier.company_name = company_name
        supplier.contact_person = _clean_text(data.get("contact_person"))
        supplier.phone = phone
        supplier.phone2 = _clean_text(data.get("phone2"))
        supplier.telegram = _clean_text(data.get("telegram"))
        supplier.address = _clean_text(data.get("address"))
        supplier.notes = _clean_text(data.get("notes"))
        return True


def delete_supplier(supplier_id: int) -> bool:
    with SessionLocal.begin() as session:
        supplier = session.get(Supplier, supplier_id)
        if supplier is None:
            return False

        has_purchases = session.scalar(
            select(func.count(Purchase.id)).where(Purchase.supplier_id == supplier_id)
        )
        if has_purchases and int(has_purchases) > 0:
            raise ValueError(t("suppliers.error.cannot_delete_has_purchases"))

        session.delete(supplier)
        return True


@ui.page("/suppliers")
@with_master_layout(t("suppliers.title"))
def suppliers_page() -> None:
    filters = {
        "search": "",
        "has_telegram": "",
        "has_phone2": "",
    }

    page_header(t("suppliers.title"), t("suppliers.description"))

    supplier_columns = [
        {"name": "company_name", "label": t("suppliers.field.company_name"), "field": "company_name", "align": "left"},
        {"name": "contact_person", "label": t("suppliers.field.contact_person"), "field": "contact_person", "align": "left"},
        {"name": "phone", "label": t("suppliers.field.phone"), "field": "phone", "align": "left"},
        {"name": "phone2", "label": t("suppliers.field.phone2"), "field": "phone2", "align": "left"},
        {"name": "telegram", "label": t("suppliers.field.telegram"), "field": "telegram", "align": "left"},
        {"name": "address", "label": t("suppliers.field.address"), "field": "address", "align": "left"},
        {"name": "notes", "label": t("common.table.notes"), "field": "notes", "align": "left"},
        {"name": "actions", "label": t("common.table.actions"), "field": "actions", "align": "center"},
    ]
    suppliers_table: Any = None

    has_telegram_options = {
        "": t("common.filter.all"),
        "yes": t("suppliers.filter.has_telegram_yes"),
        "no": t("suppliers.filter.has_telegram_no"),
    }
    has_phone2_options = {
        "": t("common.filter.all"),
        "yes": t("suppliers.filter.has_phone2_yes"),
        "no": t("suppliers.filter.has_phone2_no"),
    }

    search_input: Any = None
    telegram_select: Any = None
    phone2_select: Any = None

    def refresh_table() -> None:
        try:
            if suppliers_table is None:
                return
            suppliers_table.rows = load_suppliers(
                search=filters["search"],
                has_telegram=filters["has_telegram"],
                has_phone2=filters["has_phone2"],
            )
            suppliers_table.update()
        except SQLAlchemyError:
            ui.notify(t("suppliers.notify.load_failed"), color="negative")

    def build_supplier_form(title: str) -> tuple[ui.dialog, dict[str, Any]]:
        dialog = ui.dialog()
        with dialog, ui.card().classes("w-[700px] max-w-full"):
            ui.label(title).classes("text-h6")
            with ui.row().classes("w-full gap-2"):
                company_name = ui.input(t("suppliers.field.company_name_required")).classes("col")
                contact_person = ui.input(t("suppliers.field.contact_person")).classes("col")
            with ui.row().classes("w-full gap-2"):
                phone = ui.input(t("suppliers.field.phone_required")).classes("col")
                phone2 = ui.input(t("suppliers.field.phone2")).classes("col")
            with ui.row().classes("w-full gap-2"):
                telegram = ui.input(t("suppliers.field.telegram")).classes("col")
                address = ui.input(t("suppliers.field.address")).classes("col")
            notes = ui.textarea(t("common.table.notes")).classes("w-full")
            with ui.row().classes("justify-end w-full q-mt-sm"):
                ui.button(t("common.button.cancel"), on_click=dialog.close, color="grey-6")
                action_button = ui.button(t("common.button.save"), color="primary")

        return dialog, {
            "company_name": company_name,
            "contact_person": contact_person,
            "phone": phone,
            "phone2": phone2,
            "telegram": telegram,
            "address": address,
            "notes": notes,
            "action_button": action_button,
        }

    def form_data(inputs: dict[str, Any]) -> dict[str, Any]:
        return {
            "company_name": inputs["company_name"].value,
            "contact_person": inputs["contact_person"].value,
            "phone": inputs["phone"].value,
            "phone2": inputs["phone2"].value,
            "telegram": inputs["telegram"].value,
            "address": inputs["address"].value,
            "notes": inputs["notes"].value,
        }

    def reset_form(inputs: dict[str, Any]) -> None:
        inputs["company_name"].value = ""
        inputs["contact_person"].value = ""
        inputs["phone"].value = ""
        inputs["phone2"].value = ""
        inputs["telegram"].value = ""
        inputs["address"].value = ""
        inputs["notes"].value = ""

    def fill_form(inputs: dict[str, Any], row: dict[str, Any]) -> None:
        inputs["company_name"].value = row["company_name"]
        inputs["contact_person"].value = row["contact_person"]
        inputs["phone"].value = row["phone"]
        inputs["phone2"].value = row["phone2"]
        inputs["telegram"].value = row["telegram"]
        inputs["address"].value = row["address"]
        inputs["notes"].value = row["notes"]

    add_dialog, add_inputs = build_supplier_form(t("suppliers.dialog.add_supplier"))
    edit_dialog, edit_inputs = build_supplier_form(t("suppliers.dialog.edit_supplier"))
    edit_supplier_id: int | None = None
    delete_target: dict[str, Any] | None = None

    def open_add_dialog() -> None:
        reset_form(add_inputs)
        add_dialog.open()

    def submit_add() -> None:
        try:
            create_supplier(form_data(add_inputs))
            add_dialog.close()
            refresh_table()
            ui.notify(t("suppliers.notify.created"), color="positive")
        except ValueError as exc:
            ui.notify(str(exc), color="warning")
        except SQLAlchemyError:
            ui.notify(t("suppliers.notify.create_failed"), color="negative")

    def open_edit_dialog(row: dict[str, Any]) -> None:
        nonlocal edit_supplier_id
        edit_supplier_id = int(row["id"])
        fill_form(edit_inputs, row)
        edit_dialog.open()

    def submit_edit() -> None:
        nonlocal edit_supplier_id
        if edit_supplier_id is None:
            ui.notify(t("suppliers.notify.no_supplier_selected"), color="warning")
            return
        try:
            updated = update_supplier(edit_supplier_id, form_data(edit_inputs))
            if not updated:
                ui.notify(t("suppliers.notify.not_found"), color="warning")
                return
            edit_dialog.close()
            refresh_table()
            ui.notify(t("suppliers.notify.updated"), color="positive")
        except ValueError as exc:
            ui.notify(str(exc), color="warning")
        except SQLAlchemyError:
            ui.notify(t("suppliers.notify.update_failed"), color="negative")

    with ui.dialog() as delete_dialog, ui.card():
        delete_label = ui.label(t("suppliers.dialog.delete_supplier"))
        with ui.row().classes("justify-end w-full q-mt-sm"):
            ui.button(t("common.button.cancel"), on_click=delete_dialog.close, color="grey-6")

            def confirm_delete() -> None:
                nonlocal delete_target
                if delete_target is None:
                    delete_dialog.close()
                    return
                try:
                    deleted = delete_supplier(int(delete_target["id"]))
                    if deleted:
                        ui.notify(t("suppliers.notify.deleted"), color="positive")
                    else:
                        ui.notify(t("suppliers.notify.not_found"), color="warning")
                    refresh_table()
                    delete_dialog.close()
                except ValueError as exc:
                    ui.notify(str(exc), color="warning")
                except SQLAlchemyError:
                    ui.notify(t("suppliers.notify.delete_failed"), color="negative")

            ui.button(t("common.button.delete"), on_click=confirm_delete, color="negative")

    def open_delete_dialog(row: dict[str, Any]) -> None:
        nonlocal delete_target
        delete_target = row
        delete_label.text = t("suppliers.dialog.delete_supplier_named", name=row["company_name"])
        delete_dialog.open()

    add_inputs["action_button"].on("click", submit_add)
    edit_inputs["action_button"].on("click", submit_edit)

    with search_panel():
        with ui.row().classes("w-full items-end no-wrap gap-3"):
            search_input = ui.input(
                label=t("suppliers.search.label"),
                placeholder=t("suppliers.search.placeholder"),
                on_change=lambda e: filters.__setitem__("search", e.value or ""),
            ).classes("flex-1 min-w-0")
            ui.button(t("common.button.search"), on_click=refresh_table, icon="search")
            ui.button(t("suppliers.button.add_supplier"), on_click=open_add_dialog, icon="add", color="primary")

    with ui.row().classes("w-full items-start gap-4 no-wrap"):
        with filter_sidebar():
            telegram_select = ui.select(
                options=has_telegram_options,
                label=t("suppliers.filter.has_telegram"),
                value="",
                on_change=lambda e: filters.__setitem__("has_telegram", e.value or ""),
            ).classes("w-full")
            phone2_select = ui.select(
                options=has_phone2_options,
                label=t("suppliers.filter.has_phone2"),
                value="",
                on_change=lambda e: filters.__setitem__("has_phone2", e.value or ""),
            ).classes("w-full")

            def reset_filters() -> None:
                filters["search"] = ""
                filters["has_telegram"] = ""
                filters["has_phone2"] = ""
                search_input.value = ""
                telegram_select.value = ""
                phone2_select.value = ""
                search_input.update()
                telegram_select.update()
                phone2_select.update()
                refresh_table()

            ui.button(t("common.button.apply_filters"), on_click=refresh_table, icon="filter_alt").classes("w-full")
            ui.button(t("common.button.reset_filters"), on_click=reset_filters, icon="refresh").classes("w-full q-mt-sm")

        with data_table_card().classes("flex-1 min-w-0"):
            with ui.element("div").classes("w-full overflow-auto").style("max-height: calc(100vh - 300px);"):
                suppliers_table = ui.table(
                    columns=supplier_columns,
                    rows=[],
                    row_key="id",
                    pagination=15,
                ).classes("w-full")

    suppliers_table.add_slot(
        "body-cell-actions",
        """
        <q-td :props="props">
          <q-btn dense flat round icon="edit" color="primary"
            @click="$parent.$emit('edit_supplier', props.row)" />
          <q-btn dense flat round icon="delete" color="negative"
            @click="$parent.$emit('delete_supplier', props.row)" />
        </q-td>
        """,
    )
    suppliers_table.on("edit_supplier", lambda e: open_edit_dialog(e.args))
    suppliers_table.on("delete_supplier", lambda e: open_delete_dialog(e.args))
    add_table_empty_state(suppliers_table, t("suppliers.empty.no_suppliers"), icon="🏢")

    refresh_table()
