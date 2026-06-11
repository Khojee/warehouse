from __future__ import annotations

from typing import Any

from nicegui import ui
from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError

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
        raise ValueError("Company Name is required.")
    if not phone:
        raise ValueError("Phone is required.")

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
        raise ValueError("Company Name is required.")
    if not phone:
        raise ValueError("Phone is required.")

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
            raise ValueError("Cannot delete supplier because purchase records exist.")

        session.delete(supplier)
        return True


@ui.page("/suppliers")
@with_master_layout("Suppliers")
def suppliers_page() -> None:
    filters = {
        "search": "",
        "has_telegram": "",
        "has_phone2": "",
    }

    page_header("Suppliers", "Manage supplier companies and contact details.")

    supplier_columns = [
        {"name": "company_name", "label": "Company Name", "field": "company_name", "align": "left"},
        {"name": "contact_person", "label": "Contact Person", "field": "contact_person", "align": "left"},
        {"name": "phone", "label": "Phone", "field": "phone", "align": "left"},
        {"name": "phone2", "label": "Phone 2", "field": "phone2", "align": "left"},
        {"name": "telegram", "label": "Telegram", "field": "telegram", "align": "left"},
        {"name": "address", "label": "Address", "field": "address", "align": "left"},
        {"name": "notes", "label": "Notes", "field": "notes", "align": "left"},
        {"name": "actions", "label": "Actions", "field": "actions", "align": "center"},
    ]
    suppliers_table: Any = None

    has_telegram_options = {"": "All", "yes": "Has Telegram", "no": "No Telegram"}
    has_phone2_options = {"": "All", "yes": "Has Phone 2", "no": "No Phone 2"}

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
            ui.notify("Failed to load suppliers.", color="negative")

    def build_supplier_form(title: str) -> tuple[ui.dialog, dict[str, Any]]:
        dialog = ui.dialog()
        with dialog, ui.card().classes("w-[700px] max-w-full"):
            ui.label(title).classes("text-h6")
            with ui.row().classes("w-full gap-2"):
                company_name = ui.input("Company Name *").classes("col")
                contact_person = ui.input("Contact Person").classes("col")
            with ui.row().classes("w-full gap-2"):
                phone = ui.input("Phone *").classes("col")
                phone2 = ui.input("Phone 2").classes("col")
            with ui.row().classes("w-full gap-2"):
                telegram = ui.input("Telegram").classes("col")
                address = ui.input("Address").classes("col")
            notes = ui.textarea("Notes").classes("w-full")
            with ui.row().classes("justify-end w-full q-mt-sm"):
                ui.button("Cancel", on_click=dialog.close, color="grey-6")
                action_button = ui.button("Save", color="primary")

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

    add_dialog, add_inputs = build_supplier_form("Add Supplier")
    edit_dialog, edit_inputs = build_supplier_form("Edit Supplier")
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
            ui.notify("Supplier created successfully.", color="positive")
        except ValueError as exc:
            ui.notify(str(exc), color="warning")
        except SQLAlchemyError:
            ui.notify("Failed to create supplier.", color="negative")

    def open_edit_dialog(row: dict[str, Any]) -> None:
        nonlocal edit_supplier_id
        edit_supplier_id = int(row["id"])
        fill_form(edit_inputs, row)
        edit_dialog.open()

    def submit_edit() -> None:
        nonlocal edit_supplier_id
        if edit_supplier_id is None:
            ui.notify("No supplier selected.", color="warning")
            return
        try:
            updated = update_supplier(edit_supplier_id, form_data(edit_inputs))
            if not updated:
                ui.notify("Supplier not found.", color="warning")
                return
            edit_dialog.close()
            refresh_table()
            ui.notify("Supplier updated successfully.", color="positive")
        except ValueError as exc:
            ui.notify(str(exc), color="warning")
        except SQLAlchemyError:
            ui.notify("Failed to update supplier.", color="negative")

    with ui.dialog() as delete_dialog, ui.card():
        delete_label = ui.label("Delete supplier?")
        with ui.row().classes("justify-end w-full q-mt-sm"):
            ui.button("Cancel", on_click=delete_dialog.close, color="grey-6")

            def confirm_delete() -> None:
                nonlocal delete_target
                if delete_target is None:
                    delete_dialog.close()
                    return
                try:
                    deleted = delete_supplier(int(delete_target["id"]))
                    if deleted:
                        ui.notify("Supplier deleted successfully.", color="positive")
                    else:
                        ui.notify("Supplier not found.", color="warning")
                    refresh_table()
                    delete_dialog.close()
                except ValueError as exc:
                    ui.notify(str(exc), color="warning")
                except SQLAlchemyError:
                    ui.notify("Failed to delete supplier.", color="negative")

            ui.button("Delete", on_click=confirm_delete, color="negative")

    def open_delete_dialog(row: dict[str, Any]) -> None:
        nonlocal delete_target
        delete_target = row
        delete_label.text = f'Delete supplier "{row["company_name"]}"?'
        delete_dialog.open()

    add_inputs["action_button"].on("click", submit_add)
    edit_inputs["action_button"].on("click", submit_edit)

    with search_panel():
        with ui.row().classes("w-full items-end no-wrap gap-3"):
            search_input = ui.input(
                label="Search Supplier",
                placeholder="Search company, contact, phone, telegram",
                on_change=lambda e: filters.__setitem__("search", e.value or ""),
            ).classes("flex-1 min-w-0")
            ui.button("Search", on_click=refresh_table, icon="search")
            ui.button("Add Supplier", on_click=open_add_dialog, icon="add", color="primary")

    with ui.row().classes("w-full items-start gap-4 no-wrap"):
        with filter_sidebar():
            telegram_select = ui.select(
                options=has_telegram_options,
                label="Has Telegram",
                value="",
                on_change=lambda e: filters.__setitem__("has_telegram", e.value or ""),
            ).classes("w-full")
            phone2_select = ui.select(
                options=has_phone2_options,
                label="Has Phone 2",
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

            ui.button("Apply Filters", on_click=refresh_table, icon="filter_alt").classes("w-full")
            ui.button("Reset Filters", on_click=reset_filters, icon="refresh").classes("w-full q-mt-sm")

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
    add_table_empty_state(suppliers_table, "No suppliers found.", icon="🏢")

    refresh_table()