from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from nicegui import ui
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from core.i18n import t
from database import SessionLocal
from models import Product, ProductCategory
from pages.components import (
    add_table_empty_state,
    data_table_card,
    filter_sidebar,
    page_header,
    search_panel,
)
from pages.layout import with_master_layout
from services import excel_export, image_service, pdf_export


OTHER_CATEGORY_OPTION = "other"


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"))
    try:
        return Decimal(str(value).strip()).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, AttributeError) as exc:
        raise ValueError(t("products.error.current_price_invalid")) from exc


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def load_products(
    name: str = "",
    category_id: str = "",
    size: str = "",
    pressure: str = "",
    stock_status: str = "",
) -> list[dict[str, Any]]:
    with SessionLocal() as session:
        stmt = (
            select(Product)
            .options(
                selectinload(Product.product_category),
                selectinload(Product.images),
            )
            .order_by(Product.id.desc())
        )
        if name.strip():
            stmt = stmt.where(Product.name.ilike(f"%{name.strip()}%"))
        if category_id.strip():
            try:
                stmt = stmt.where(Product.category_id == int(category_id.strip()))
            except ValueError:
                stmt = stmt.where(Product.id == -1)
        if size.strip():
            stmt = stmt.where(Product.size == size.strip())
        if pressure.strip():
            stmt = stmt.where(Product.pressure == pressure.strip())
        if stock_status == "in_stock":
            stmt = stmt.where(Product.min_stock <= 0)
        elif stock_status == "low_stock":
            stmt = stmt.where(Product.min_stock > 0)

        products = session.scalars(stmt).all()
        return [_product_to_row(product) for product in products]


def load_products_by_ids(product_ids: set[int] | list[int]) -> list[dict[str, Any]]:
    ids = sorted({int(pid) for pid in product_ids})
    if not ids:
        return []
    with SessionLocal() as session:
        products = session.scalars(
            select(Product)
            .options(
                selectinload(Product.product_category),
                selectinload(Product.images),
            )
            .where(Product.id.in_(ids))
            .order_by(Product.id.desc())
        ).all()
    return [_product_to_row(product) for product in products]


def _primary_image_url(product: Product) -> str:
    images = sorted(product.images, key=lambda img: not img.is_primary)
    for image in images:
        relative = (image.file_path or "").strip().replace("\\", "/")
        if relative and (image_service.PROJECT_ROOT / relative).exists():
            return f"/{relative}"
    return ""


def _product_to_row(product: Product) -> dict[str, Any]:
    return {
        "id": product.id,
        "image_url": _primary_image_url(product),
        "name": product.name,
        "category_id": product.category_id or "",
        "category": (
            product.product_category.name
            if product.product_category is not None
            else (product.category or "")
        ),
        "size": product.size or "",
        "pressure": product.pressure or "",
        "material": product.material or "",
        "unit": product.unit,
        "current_price": f"{product.current_price:.2f}",
        "min_stock": product.min_stock,
        "description": product.description or "",
    }

def load_filter_options() -> dict[str, list[str]]:
    with SessionLocal() as session:
        categories = session.scalars(
            select(ProductCategory.name)
            .distinct()
            .order_by(ProductCategory.name.asc())
        ).all()
        sizes = session.scalars(
            select(Product.size)
            .where(Product.size.is_not(None))
            .distinct()
            .order_by(Product.size.asc())
        ).all()
        pressures = session.scalars(
            select(Product.pressure)
            .where(Product.pressure.is_not(None))
            .distinct()
            .order_by(Product.pressure.asc())
        ).all()

    return {
        "categories": [value for value in categories if value],
        "sizes": [value for value in sizes if value],
        "pressures": [value for value in pressures if value],
    }


def load_categories() -> list[ProductCategory]:
    with SessionLocal() as session:
        return session.scalars(
            select(ProductCategory).order_by(func.lower(ProductCategory.name).asc())
        ).all()


def find_category_by_name(name: str) -> ProductCategory | None:
    normalized = name.strip().lower()
    if not normalized:
        return None
    with SessionLocal() as session:
        return session.scalars(
            select(ProductCategory).where(func.lower(ProductCategory.name) == normalized)
        ).first()


def create_category(name: str) -> ProductCategory:
    cleaned_name = name.strip()
    if not cleaned_name:
        raise ValueError(t("products.error.category_name_empty"))
    if len(cleaned_name) < 2:
        raise ValueError(t("products.error.category_name_short"))

    if find_category_by_name(cleaned_name) is not None:
        raise ValueError(t("products.error.category_exists"))

    with SessionLocal() as session:
        category = ProductCategory(name=cleaned_name)
        session.add(category)
        session.commit()
        session.refresh(category)
        return category


def create_product(data: dict[str, Any]) -> Product:
    name = str(data.get("name", "")).strip()
    if not name:
        raise ValueError(t("products.error.name_required"))

    unit = str(data.get("unit", "pcs")).strip() or "pcs"
    try:
        min_stock = int(data.get("min_stock", 0) or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError(t("products.error.min_stock_integer")) from exc
    if min_stock < 0:
        raise ValueError(t("products.error.min_stock_negative"))

    with SessionLocal() as session:
        raw_category_id = str(data.get("category_id", "")).strip()
        if raw_category_id == OTHER_CATEGORY_OPTION:
            raise ValueError(t("products.error.create_select_category"))
        try:
            category_id = int(raw_category_id) if raw_category_id else None
        except ValueError as exc:
            raise ValueError(t("products.error.select_valid_category")) from exc
        category_name: str | None = None
        if category_id is not None:
            category = session.get(ProductCategory, category_id)
            if category is None:
                raise ValueError(t("products.error.select_valid_category_exclamation"))
            category_name = category.name

        product = Product(
            name=name,
            category_id=category_id,
            category=category_name,
            size=_clean_text(data.get("size")),
            pressure=_clean_text(data.get("pressure")),
            material=_clean_text(data.get("material")),
            unit=unit,
            current_price=_to_decimal(data.get("current_price", "0")),
            min_stock=min_stock,
            description=_clean_text(data.get("description")),
        )

        session.add(product)
        session.commit()
        session.refresh(product)
        return product


def update_product(product_id: int, data: dict[str, Any]) -> bool:
    name = str(data.get("name", "")).strip()
    if not name:
        raise ValueError(t("products.error.name_required"))

    try:
        min_stock = int(data.get("min_stock", 0) or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError(t("products.error.min_stock_integer")) from exc
    if min_stock < 0:
        raise ValueError(t("products.error.min_stock_negative"))

    with SessionLocal() as session:
        product = session.get(Product, product_id)
        if product is None:
            return False

        raw_category_id = str(data.get("category_id", "")).strip()
        if raw_category_id == OTHER_CATEGORY_OPTION:
            raise ValueError(t("products.error.create_select_category"))
        try:
            category_id = int(raw_category_id) if raw_category_id else None
        except ValueError as exc:
            raise ValueError(t("products.error.select_valid_category")) from exc
        category_name: str | None = None
        if category_id is not None:
            category = session.get(ProductCategory, category_id)
            if category is None:
                raise ValueError(t("products.error.select_valid_category_exclamation"))
            category_name = category.name

        product.name = name
        product.category_id = category_id
        product.category = category_name
        product.size = _clean_text(data.get("size"))
        product.pressure = _clean_text(data.get("pressure"))
        product.material = _clean_text(data.get("material"))
        product.unit = str(data.get("unit", "pcs")).strip() or "pcs"
        product.current_price = _to_decimal(data.get("current_price", "0"))
        product.min_stock = min_stock
        product.description = _clean_text(data.get("description"))

        session.commit()
        return True


def delete_product(product_id: int) -> bool:
    with SessionLocal() as session:
        product = session.get(Product, product_id)
        if product is None:
            return False

        session.delete(product)
        session.commit()
        return True


@ui.page("/products")
@with_master_layout(t("products.title"))
def products_page() -> None:
    # Column width only — does not scale/shrink the checkbox itself.
    ui.add_css(
        """
        .fc-products-table .q-table th.q-table--col-auto-width,
        .fc-products-table .q-table td.q-table--col-auto-width {
            width: 48px !important;
            min-width: 48px !important;
            max-width: 48px !important;
            text-align: center;
            vertical-align: middle;
            padding-left: 0;
            padding-right: 0;
        }
        """
    )
    page_header(t("products.title"), t("products.description"))

    filters = {
        "name": "",
        "category_id": "",
        "size": "",
        "pressure": "",
        "stock_status": "",
    }
    selected_row: dict[str, Any] | None = None
    editing_product_id: int | None = None
    # Persist checkbox selection across filter/search refreshes for this page session.
    selected_product_ids: set[int] = set()
    pending_export_format: Literal["pdf", "excel"] | None = None
    export_options: dict[str, Any] = {
        "images": True,
        "prices": True,
        "category": True,
        "material": True,
        "pressure": True,
        "unit": True,
        "description": True,
        "orientation": "portrait",
    }
    filtered_rows: list[dict[str, Any]] = []
    syncing_selection = False
    syncing_select_all = False
    select_all_checkbox: Any = None

    columns = [
        {"name": "image", "label": t("common.table.image"), "field": "image_url", "align": "center"},
        {"name": "name", "label": t("products.field.name"), "field": "name", "align": "left"},
        {"name": "category", "label": t("products.field.category"), "field": "category", "align": "left"},
        {"name": "size", "label": t("products.field.size"), "field": "size", "align": "left"},
        {"name": "pressure", "label": t("products.field.pressure"), "field": "pressure", "align": "left"},
        {"name": "material", "label": t("products.field.material"), "field": "material", "align": "left"},
        {"name": "unit", "label": t("products.field.unit"), "field": "unit", "align": "left"},
        {
            "name": "current_price",
            "label": t("products.field.current_price"),
            "field": "current_price",
            "align": "right",
        },
        {"name": "min_stock", "label": t("products.field.min_stock"), "field": "min_stock", "align": "right"},
        {"name": "description", "label": t("products.field.description"), "field": "description", "align": "left"},
        {"name": "actions", "label": t("common.table.actions"), "field": "actions", "align": "center"},
    ]

    table: Any = None
    category_filter_options: dict[str, str] = {"": t("common.filter.all")}
    category_form_options: dict[str, str] = {
        "": t("products.option.select_category"),
        OTHER_CATEGORY_OPTION: t("products.option.other_category"),
    }
    size_filter_options: dict[str, str] = {"": t("common.filter.all")}
    pressure_filter_options: dict[str, str] = {"": t("common.filter.all")}
    stock_status_filter_options: dict[str, str] = {
        "": t("common.filter.all"),
        "in_stock": t("products.filter.normal"),
        "low_stock": t("products.filter.low_stock"),
    }
    unit_options: dict[str, str] = {
        t("products.unit.pcs"): t("products.unit.pcs"),
        t("products.unit.kg"): t("products.unit.kg"),
        t("products.unit.meter"): t("products.unit.meter"),
    }

    category_select: Any = None
    size_select: Any = None
    pressure_select: Any = None
    stock_status_select: Any = None
    pending_category_target = "add"
    pending_category_name = ""

    def refresh_table() -> None:
        try:
            options = load_filter_options()
            categories = load_categories()

            category_filter_options.clear()
            category_filter_options.update(
                {"": t("common.filter.all"), **{str(category.id): category.name for category in categories}}
            )
            category_form_options.clear()
            category_form_options.update(
                {str(category.id): category.name for category in categories}
            )
            category_form_options[""] = t("products.option.select_category")
            category_form_options[OTHER_CATEGORY_OPTION] = t("products.option.other_category")
            size_filter_options.clear()
            size_filter_options.update({"": t("common.filter.all"), **{v: v for v in options["sizes"]}})
            pressure_filter_options.clear()
            pressure_filter_options.update({"": t("common.filter.all"), **{v: v for v in options["pressures"]}})

            if filters["category_id"] not in category_filter_options:
                filters["category_id"] = ""
            if filters["size"] not in size_filter_options:
                filters["size"] = ""
            if filters["pressure"] not in pressure_filter_options:
                filters["pressure"] = ""

            if category_select is not None:
                category_select.options = category_filter_options
                category_select.update()
            if size_select is not None:
                size_select.options = size_filter_options
                size_select.update()
            if pressure_select is not None:
                pressure_select.options = pressure_filter_options
                pressure_select.update()

            if table is None:
                return

            rows = load_products(
                name=filters["name"],
                category_id=filters["category_id"],
                size=filters["size"],
                pressure=filters["pressure"],
                stock_status=filters["stock_status"],
            )
            filtered_rows.clear()
            filtered_rows.extend(rows)
            table.rows = rows
            # Keep ID-based selection across filters/search/pagination;
            # only sync checkboxes for rows present in the current result set.
            sync_table_selection_from_ids()
            update_selection_count()
            update_select_all_checkbox()
        except SQLAlchemyError:
            ui.notify(t("products.notify.load_failed"), color="negative")

    def build_form(dialog_title: str, form_target: str) -> tuple[ui.dialog, dict[str, Any]]:
        dialog = ui.dialog()
        with dialog, ui.card().classes("w-[700px] max-w-full"):
            ui.label(dialog_title).classes("text-h6")
            with ui.row().classes("w-full gap-2"):
                name_input = ui.input(t("products.field.name")).classes("col")
                category_input = ui.select(
                    options=category_form_options,
                    label=t("products.field.category"),
                    with_input=True,
                    value="",
                    on_change=lambda e: handle_category_select(
                        form_target,
                        getattr(e, "value", None),
                    ),
                ).classes("col")
            with ui.row().classes("w-full gap-2"):
                size_input = ui.input(t("products.field.size")).classes("col")
                pressure_input = ui.input(t("products.field.pressure")).classes("col")
            with ui.row().classes("w-full gap-2"):
                material_input = ui.input(t("products.field.material")).classes("col")
                unit_input = ui.select(
                    options=unit_options,
                    label=t("products.field.unit"),
                    value=t("products.unit.pcs"),
                ).classes("col")
            with ui.row().classes("w-full gap-2"):
                current_price_input = ui.input(t("products.field.current_price")).classes("col")
                min_stock_input = ui.number(t("products.field.min_stock"), value=0, precision=0).classes(
                    "col"
                )
            description_input = ui.textarea(t("products.field.description")).classes("w-full")

            image_state: dict[str, Any] = {"data": None, "ext": None, "name": ""}
            image_status_label: Any = None

            async def handle_image_upload(e: Any) -> None:
                ext = image_service.extension_of(e.file.name)
                if ext is None:
                    ui.notify(
                        t("products.image.invalid_format"),
                        color="warning",
                    )
                    image_upload.reset()
                    return
                image_state["data"] = await e.file.read()
                image_state["ext"] = ext
                image_state["name"] = e.file.name
                image_status_label.text = t("products.image.selected", filename=e.file.name)

            image_upload = (
                ui.upload(
                    label=t("products.field.product_image"),
                    auto_upload=True,
                    max_file_size=10 * 1024 * 1024,
                    on_upload=handle_image_upload,
                )
                .props('accept=".png,.jpg,.jpeg,.webp" flat bordered')
                .classes("w-full")
            )
            image_status_label = ui.label("").classes("text-caption text-grey-7")

            with ui.row().classes("justify-end w-full q-mt-md"):
                ui.button(t("common.button.cancel"), on_click=dialog.close, color="grey-6")
                action_button = ui.button(t("common.button.save"))

        inputs: dict[str, Any] = {
            "name": name_input,
            "category": category_input,
            "size": size_input,
            "pressure": pressure_input,
            "material": material_input,
            "unit": unit_input,
            "current_price": current_price_input,
            "min_stock": min_stock_input,
            "description": description_input,
            "image_state": image_state,
            "image_upload": image_upload,
            "image_status": image_status_label,
            "action_button": action_button,
        }
        return dialog, inputs

    add_dialog, add_inputs = build_form(t("products.dialog.add_product"), "add")
    edit_dialog, edit_inputs = build_form(t("products.dialog.edit_product"), "edit")

    def _form_data(inputs: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": inputs["name"].value,
            "category_id": inputs["category"].value,
            "size": inputs["size"].value,
            "pressure": inputs["pressure"].value,
            "material": inputs["material"].value,
            "unit": inputs["unit"].value,
            "current_price": inputs["current_price"].value,
            "min_stock": inputs["min_stock"].value,
            "description": inputs["description"].value,
        }

    def _clear_image_field(inputs: dict[str, Any], current_image: str = "") -> None:
        inputs["image_state"].update(data=None, ext=None, name="")
        inputs["image_upload"].reset()
        inputs["image_status"].text = (
            t("products.image.will_replace")
            if current_image
            else ""
        )

    def _save_uploaded_image(inputs: dict[str, Any], product_id: int) -> None:
        state = inputs["image_state"]
        if not state.get("data"):
            return
        category_value = str(inputs["category"].value or "")
        category_name = (
            category_form_options.get(category_value, "")
            if category_value not in {"", OTHER_CATEGORY_OPTION}
            else ""
        )
        try:
            file_path = image_service.save_product_image(
                state["data"],
                category=category_name,
                size=str(inputs["size"].value or ""),
                pressure=str(inputs["pressure"].value or ""),
                ext=state["ext"],
            )
            image_service.upsert_primary_product_image(product_id, file_path)
        except (OSError, SQLAlchemyError):
            ui.notify(t("products.notify.image_upload_failed"), color="warning")

    def _reset_form(inputs: dict[str, Any]) -> None:
        inputs["name"].value = ""
        inputs["category"].value = ""
        inputs["size"].value = ""
        inputs["pressure"].value = ""
        inputs["material"].value = ""
        inputs["unit"].value = t("products.unit.pcs")
        inputs["current_price"].value = "0.00"
        inputs["min_stock"].value = 0
        inputs["description"].value = ""
        _clear_image_field(inputs)

    def _fill_form(inputs: dict[str, Any], row: dict[str, Any]) -> None:
        inputs["name"].value = row["name"]
        inputs["category"].value = str(row["category_id"]) if row["category_id"] else ""
        inputs["size"].value = row["size"]
        inputs["pressure"].value = row["pressure"]
        inputs["material"].value = row["material"]
        inputs["unit"].value = row["unit"]
        inputs["current_price"].value = row["current_price"]
        inputs["min_stock"].value = row["min_stock"]
        inputs["description"].value = row["description"]
        _clear_image_field(inputs, current_image=str(row.get("image_url") or ""))

    with ui.dialog() as create_category_dialog, ui.card().classes("w-[420px] max-w-full"):
        ui.label(t("products.dialog.create_category")).classes("text-h6")
        category_name_input = ui.input(t("products.field.category_name")).classes("w-full")
        with ui.row().classes("justify-end w-full q-mt-sm"):
            ui.button(t("common.button.cancel"), on_click=create_category_dialog.close, color="grey-6")

            def validate_new_category() -> None:
                nonlocal pending_category_name
                candidate = (category_name_input.value or "").strip()
                if not candidate:
                    ui.notify(t("products.notify.category_name_empty"), color="warning")
                    return
                if len(candidate) < 2:
                    ui.notify(t("products.notify.category_name_short"), color="warning")
                    return
                if find_category_by_name(candidate) is not None:
                    ui.notify(t("products.notify.category_exists"), color="warning")
                    return
                pending_category_name = candidate
                confirmation_message.text = t(
                    "products.dialog.confirm_create_category",
                    name=candidate,
                )
                create_category_dialog.close()
                confirm_create_dialog.open()

            ui.button(t("common.button.save"), on_click=validate_new_category, color="primary")

    with ui.dialog() as confirm_create_dialog, ui.card().classes("w-[430px] max-w-full"):
        ui.label(t("products.dialog.create_category")).classes("text-h6")
        confirmation_message = ui.label("")
        with ui.row().classes("justify-end w-full q-mt-sm"):
            ui.button(t("common.button.cancel"), on_click=confirm_create_dialog.close, color="grey-6")

            def confirm_create_category() -> None:
                nonlocal pending_category_name
                try:
                    created = create_category(pending_category_name)
                except ValueError as exc:
                    ui.notify(str(exc), color="warning")
                    confirm_create_dialog.close()
                    return
                except SQLAlchemyError:
                    ui.notify(t("products.notify.category_create_failed"), color="negative")
                    confirm_create_dialog.close()
                    return

                refresh_table()
                add_inputs["category"].options = category_form_options
                add_inputs["category"].update()
                edit_inputs["category"].options = category_form_options
                edit_inputs["category"].update()
                add_inputs["category"].value = str(created.id)
                add_inputs["category"].update()
                if pending_category_target == "edit":
                    edit_inputs["category"].value = str(created.id)
                    edit_inputs["category"].update()
                ui.notify(t("products.notify.category_created"), color="positive")
                pending_category_name = ""
                confirm_create_dialog.close()

            ui.button(t("common.button.create"), on_click=confirm_create_category, color="primary")

    def _normalize_category_choice(selected_value: Any) -> str:
        if selected_value is None:
            return ""
        if isinstance(selected_value, (list, tuple)):
            if not selected_value:
                return ""
            return _normalize_category_choice(selected_value[0])
        if isinstance(selected_value, dict):
            value = selected_value.get("value")
            if value is not None:
                return str(value)
            label = selected_value.get("label")
            return str(label or "")
        if hasattr(selected_value, "value"):
            return str(getattr(selected_value, "value") or "")
        return str(selected_value or "")

    def handle_category_select(target: str, selected_value: Any) -> None:
        nonlocal pending_category_target
        value = _normalize_category_choice(selected_value)
        if value not in {
            OTHER_CATEGORY_OPTION,
            t("products.option.other_category"),
            t("products.option.other_category_alt"),
        }:
            return
        pending_category_target = target
        target_inputs = add_inputs if target == "add" else edit_inputs
        target_inputs["category"].value = ""
        target_inputs["category"].update()
        category_name_input.value = ""
        confirmation_message.text = ""
        create_category_dialog.open()

    add_inputs["category"].on("update:model-value", lambda e: handle_category_select("add", e.args))
    edit_inputs["category"].on("update:model-value", lambda e: handle_category_select("edit", e.args))

    def on_add_product() -> None:
        try:
            product = create_product(_form_data(add_inputs))
            _save_uploaded_image(add_inputs, product.id)
            add_dialog.close()
            refresh_table()
            ui.notify(t("products.notify.product_created"), color="positive")
        except ValueError as exc:
            ui.notify(str(exc), color="warning")
        except SQLAlchemyError:
            ui.notify(t("products.notify.product_create_failed"), color="negative")

    def on_open_edit(row: dict[str, Any]) -> None:
        nonlocal editing_product_id
        editing_product_id = int(row["id"])
        add_inputs["category"].options = category_form_options
        add_inputs["category"].update()
        edit_inputs["category"].options = category_form_options
        edit_inputs["category"].update()
        _fill_form(edit_inputs, row)
        edit_dialog.open()

    def on_update_product() -> None:
        nonlocal editing_product_id
        if editing_product_id is None:
            ui.notify(t("products.notify.no_product_selected"), color="warning")
            return

        try:
            updated = update_product(editing_product_id, _form_data(edit_inputs))
            if not updated:
                ui.notify(t("products.notify.product_not_found"), color="warning")
                return
            _save_uploaded_image(edit_inputs, editing_product_id)
            edit_dialog.close()
            refresh_table()
            ui.notify(t("products.notify.product_updated"), color="positive")
        except ValueError as exc:
            ui.notify(str(exc), color="warning")
        except SQLAlchemyError:
            ui.notify(t("products.notify.product_update_failed"), color="negative")

    with ui.dialog() as delete_dialog, ui.card():
        delete_message = ui.label(t("products.dialog.delete_product"))
        with ui.row().classes("justify-end w-full"):
            ui.button(t("common.button.cancel"), on_click=delete_dialog.close, color="grey-6")

            def confirm_delete() -> None:
                nonlocal selected_row
                if selected_row is None:
                    delete_dialog.close()
                    return
                try:
                    product_id = int(selected_row["id"])
                    deleted = delete_product(product_id)
                    if deleted:
                        selected_product_ids.discard(product_id)
                        ui.notify(t("products.notify.product_deleted"), color="positive")
                    else:
                        ui.notify(t("products.notify.product_not_found"), color="warning")
                    refresh_table()
                except SQLAlchemyError:
                    ui.notify(t("products.notify.product_delete_failed"), color="negative")
                finally:
                    delete_dialog.close()
                    selected_row = None

            ui.button(t("common.button.delete"), on_click=confirm_delete, color="negative")

    def on_open_delete(row: dict[str, Any]) -> None:
        nonlocal selected_row
        selected_row = row
        delete_message.text = t("products.dialog.delete_product_named", name=row["name"])
        delete_dialog.open()

    add_inputs["action_button"].on("click", on_add_product)
    edit_inputs["action_button"].on("click", on_update_product)

    def open_add_dialog() -> None:
        add_inputs["category"].options = category_form_options
        add_inputs["category"].update()
        _reset_form(add_inputs)
        add_dialog.open()

    def filtered_product_ids() -> set[int]:
        return {int(row["id"]) for row in filtered_rows}

    def sync_table_selection_from_ids() -> None:
        nonlocal syncing_selection
        if table is None:
            return
        syncing_selection = True
        try:
            table.selected = [
                row for row in filtered_rows if int(row["id"]) in selected_product_ids
            ]
            table.update()
        finally:
            syncing_selection = False

    def update_selection_count() -> None:
        selection_count_label.text = t(
            "products.selection.count",
            count=len(selected_product_ids),
        )

    def update_select_all_checkbox() -> None:
        nonlocal syncing_select_all
        if select_all_checkbox is None:
            return
        filtered_ids = filtered_product_ids()
        selected_in_filter = selected_product_ids.intersection(filtered_ids)
        syncing_select_all = True
        try:
            if filtered_ids and filtered_ids.issubset(selected_product_ids):
                select_all_checkbox.value = True
                select_all_checkbox.props(remove="indeterminate")
            elif selected_in_filter:
                select_all_checkbox.value = False
                select_all_checkbox.props(add="indeterminate")
            else:
                select_all_checkbox.value = False
                select_all_checkbox.props(remove="indeterminate")
            select_all_checkbox.update()
        finally:
            syncing_select_all = False

    def on_table_select(_: Any = None) -> None:
        if table is None or syncing_selection:
            return
        # Update only IDs in the current filter result; keep out-of-filter selections.
        filtered_ids = filtered_product_ids()
        ui_selected_filtered = {int(row["id"]) for row in table.selected}
        selected_product_ids.difference_update(filtered_ids)
        selected_product_ids.update(ui_selected_filtered)
        update_selection_count()
        update_select_all_checkbox()

    def on_select_all_header(_: Any = None) -> None:
        """Toggle filter-wide Select All (same scope as filtered search results)."""
        if syncing_select_all:
            return
        filtered_ids = filtered_product_ids()
        if not filtered_ids:
            update_select_all_checkbox()
            return
        # Toggle from current ID state so uncheck works even if Vue passes a stale value.
        if filtered_ids.issubset(selected_product_ids):
            selected_product_ids.difference_update(filtered_ids)
        else:
            selected_product_ids.update(filtered_ids)
        sync_table_selection_from_ids()
        update_selection_count()
        update_select_all_checkbox()

    def clear_all_selection() -> None:
        selected_product_ids.clear()
        sync_table_selection_from_ids()
        update_selection_count()
        update_select_all_checkbox()

    def resolve_export_rows() -> list[dict[str, Any]]:
        """Selected products (by ID) if any; otherwise all currently filtered rows."""
        if selected_product_ids:
            return load_products_by_ids(selected_product_ids)
        return list(filtered_rows)

    def build_catalog_columns(options: dict[str, Any]) -> list[dict[str, Any]]:
        columns_out: list[dict[str, Any]] = []
        if options.get("images", True):
            columns_out.append(
                {
                    "name": "image",
                    "label": t("products.export.column.image"),
                    "field": "image_url",
                    "align": "center",
                }
            )
        columns_out.append(
            {
                "name": "name",
                "label": t("products.field.name"),
                "field": "name",
                "align": "left",
            }
        )
        if options.get("category", True):
            columns_out.append(
                {
                    "name": "category",
                    "label": t("products.field.category"),
                    "field": "category",
                    "align": "left",
                }
            )
        columns_out.append(
            {
                "name": "size",
                "label": t("products.field.size"),
                "field": "size",
                "align": "left",
            }
        )
        if options.get("pressure", True):
            columns_out.append(
                {
                    "name": "pressure",
                    "label": t("products.field.pressure"),
                    "field": "pressure",
                    "align": "left",
                }
            )
        if options.get("material", True):
            columns_out.append(
                {
                    "name": "material",
                    "label": t("products.field.material"),
                    "field": "material",
                    "align": "left",
                }
            )
        if options.get("unit", True):
            columns_out.append(
                {
                    "name": "unit",
                    "label": t("products.field.unit"),
                    "field": "unit",
                    "align": "left",
                }
            )
        if options.get("prices", True):
            columns_out.append(
                {
                    "name": "current_price",
                    "label": t("products.field.current_price"),
                    "field": "current_price",
                    "align": "right",
                }
            )
        if options.get("description", True):
            columns_out.append(
                {
                    "name": "description",
                    "label": t("products.field.description"),
                    "field": "description",
                    "align": "left",
                }
            )
        return columns_out

    def render_export_preview(rows: list[dict[str, Any]]) -> None:
        export_preview_container.clear()
        with export_preview_container:
            preview_rows = rows[:20]
            for row in preview_rows:
                with ui.row().classes("w-full items-center gap-3 q-py-xs no-wrap"):
                    image_url = str(row.get("image_url") or "")
                    if image_url:
                        ui.image(image_url).classes("rounded").style(
                            "width:48px;height:48px;object-fit:cover;flex:0 0 auto;"
                        )
                    else:
                        ui.icon("image", size="28px").classes("text-grey-5")
                    with ui.column().classes("gap-0 min-w-0 flex-1"):
                        ui.label(str(row.get("name") or "")).classes("text-weight-medium")
                        meta = " · ".join(
                            part
                            for part in [
                                str(row.get("category") or ""),
                                str(row.get("size") or ""),
                                str(row.get("pressure") or ""),
                                str(row.get("material") or ""),
                            ]
                            if part
                        )
                        if meta:
                            ui.label(meta).classes("text-caption text-grey-7")
                    ui.label(str(row.get("current_price") or "")).classes("text-weight-medium")
            remaining = len(rows) - len(preview_rows)
            if remaining > 0:
                ui.label(t("products.export.more_items", count=remaining)).classes(
                    "text-caption text-grey-7 q-mt-sm"
                )

    def open_export_dialog(export_format: Literal["pdf", "excel"]) -> None:
        nonlocal pending_export_format
        rows = resolve_export_rows()
        if not rows:
            ui.notify(t("products.notify.export_empty"), color="warning")
            return
        pending_export_format = export_format
        if selected_product_ids:
            export_selected_count_label.text = t(
                "products.export.selected_count",
                count=len(selected_product_ids),
            )
        else:
            export_selected_count_label.text = t(
                "products.export.selected_count",
                count=len(filtered_rows),
            )
        export_filtered_count_label.text = t(
            "products.export.filtered_count",
            count=len(filtered_rows),
        )
        option_images.value = export_options["images"]
        option_prices.value = export_options["prices"]
        option_category.value = export_options["category"]
        option_material.value = export_options["material"]
        option_pressure.value = export_options["pressure"]
        option_unit.value = export_options["unit"]
        option_description.value = export_options["description"]
        orientation_select.value = export_options.get("orientation") or "portrait"
        orientation_select.set_visibility(export_format == "pdf")
        render_export_preview(rows)
        export_dialog.open()

    def confirm_export() -> None:
        nonlocal pending_export_format
        rows = resolve_export_rows()
        if not rows or pending_export_format is None:
            ui.notify(t("products.notify.export_empty"), color="warning")
            export_dialog.close()
            return

        export_options["images"] = bool(option_images.value)
        export_options["prices"] = bool(option_prices.value)
        export_options["category"] = bool(option_category.value)
        export_options["material"] = bool(option_material.value)
        export_options["pressure"] = bool(option_pressure.value)
        export_options["unit"] = bool(option_unit.value)
        export_options["description"] = bool(option_description.value)
        export_options["orientation"] = str(orientation_select.value or "portrait")

        catalog_columns = build_catalog_columns(export_options)
        title = t("products.export.catalog_title")
        export_format = pending_export_format
        try:
            if export_format == "pdf":
                content = pdf_export.build_catalog_pdf(
                    report_title=title,
                    columns=catalog_columns,
                    rows=rows,
                    landscape_orientation=export_options["orientation"] == "landscape",
                )
                pdf_export.save_report_pdf(content, report_type="product_catalog")
                filename = f"product_catalog_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                ui.download.content(content, filename, media_type="application/pdf")
                ui.notify(t("products.notify.export_pdf_ready"), color="positive")
            else:
                content = excel_export.build_catalog_workbook(
                    report_title=title,
                    columns=catalog_columns,
                    rows=rows,
                )
                excel_export.save_report_workbook(content, report_type="product_catalog")
                filename = f"product_catalog_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                ui.download.content(content, filename)
                ui.notify(t("products.notify.export_excel_ready"), color="positive")
        except Exception:
            ui.notify(t("products.notify.export_failed"), color="negative")
        finally:
            pending_export_format = None
            export_dialog.close()

    export_dialog = ui.dialog()
    with export_dialog, ui.card().classes("w-[720px] max-w-full"):
        ui.label(t("products.export.dialog_title")).classes("text-h6")
        with ui.column().classes("w-full gap-1 q-mt-sm"):
            with ui.row().classes("w-full items-center gap-2"):
                ui.label(t("products.export.selected_label")).classes("text-weight-medium")
                export_selected_count_label = ui.label("").classes("text-weight-bold")
            with ui.row().classes("w-full items-center gap-2"):
                ui.label(t("products.export.filtered_label")).classes("text-weight-medium")
                export_filtered_count_label = ui.label("").classes("text-weight-bold")

        export_preview_container = ui.column().classes(
            "w-full q-mt-md gap-1 max-h-[280px] overflow-auto"
        )

        ui.separator().classes("q-my-md")
        with ui.column().classes("w-full gap-1"):
            option_images = ui.checkbox(t("products.export.option.images"), value=True)
            option_prices = ui.checkbox(t("products.export.option.prices"), value=True)
            option_category = ui.checkbox(t("products.export.option.category"), value=True)
            option_material = ui.checkbox(t("products.export.option.material"), value=True)
            option_pressure = ui.checkbox(t("products.export.option.pressure"), value=True)
            option_unit = ui.checkbox(t("products.export.option.unit"), value=True)
            option_description = ui.checkbox(
                t("products.export.option.description"),
                value=True,
            )
            orientation_select = ui.select(
                options={
                    "portrait": t("products.export.orientation.portrait"),
                    "landscape": t("products.export.orientation.landscape"),
                },
                label=t("products.export.option.orientation"),
                value="portrait",
            ).classes("w-full q-mt-sm")

        with ui.row().classes("w-full justify-end gap-2 q-mt-md"):
            ui.button(
                t("products.export.cancel"),
                on_click=export_dialog.close,
                color="grey-6",
            )
            ui.button(
                t("products.export.confirm"),
                on_click=confirm_export,
                color="primary",
            )

    with ui.row().classes("w-full items-start gap-4 no-wrap"):
        with filter_sidebar():
            category_select = ui.select(
                options=category_filter_options,
                label=t("products.field.category"),
                value="",
                on_change=lambda e: filters.__setitem__("category_id", e.value or ""),
                with_input=True,
            ).classes("w-full q-mb-sm")
            pressure_select = ui.select(
                options=pressure_filter_options,
                label=t("products.field.pressure"),
                value="",
                on_change=lambda e: filters.__setitem__("pressure", e.value or ""),
            ).classes("w-full q-mb-sm")
            size_select = ui.select(
                options=size_filter_options,
                label=t("products.field.size"),
                value="",
                on_change=lambda e: filters.__setitem__("size", e.value or ""),
            ).classes("w-full q-mb-sm")
            stock_status_select = ui.select(
                options=stock_status_filter_options,
                label=t("products.filter.stock_status"),
                value="",
                on_change=lambda e: filters.__setitem__("stock_status", e.value or ""),
            ).classes("w-full q-mb-md")

            def clear_filters() -> None:
                filters["name"] = ""
                filters["category_id"] = ""
                filters["size"] = ""
                filters["pressure"] = ""
                filters["stock_status"] = ""
                category_select.value = ""
                pressure_select.value = ""
                size_select.value = ""
                stock_status_select.value = ""
                category_select.update()
                pressure_select.update()
                size_select.update()
                stock_status_select.update()
                refresh_table()

            ui.button(t("common.button.reset_filters"), on_click=clear_filters, icon="refresh").classes(
                "w-full"
            )
            ui.button(t("common.button.apply_filters"), on_click=refresh_table, icon="filter_alt").classes(
                "w-full q-mt-sm"
            )

        with ui.column().classes("flex-1 min-w-0"):
            with search_panel():
                with ui.row().classes("w-full items-end no-wrap gap-3 flex-wrap"):
                    ui.input(
                        label=t("products.search.label"),
                        placeholder=t("products.search.placeholder"),
                        on_change=lambda e: filters.__setitem__("name", e.value or ""),
                    ).classes("flex-1 min-w-[180px]")
                    ui.button(t("common.button.search"), on_click=refresh_table, icon="search")
                    ui.button(
                        t("products.button.add_product"),
                        on_click=open_add_dialog,
                        icon="add",
                    )
                    ui.button(
                        t("products.button.export_pdf"),
                        on_click=lambda: open_export_dialog("pdf"),
                        icon="picture_as_pdf",
                        color="primary",
                    )
                    ui.button(
                        t("products.button.export_excel"),
                        on_click=lambda: open_export_dialog("excel"),
                        icon="table_view",
                        color="positive",
                    )

            with ui.row().classes(
                "w-full items-center gap-3 q-mb-sm flex-wrap no-wrap"
            ):
                selection_count_label = ui.label(
                    t("products.selection.count", count=0)
                ).classes("text-subtitle2 text-grey-8")
                ui.space()
                ui.button(
                    t("products.selection.clear"),
                    on_click=clear_all_selection,
                    icon="deselect",
                    color="grey-6",
                ).props("flat dense")

            with data_table_card():
                table = ui.table(
                    columns=columns,
                    rows=[],
                    row_key="id",
                    pagination=10,
                    selection="multiple",
                    on_select=on_table_select,
                ).classes("w-full fc-products-table")

    # Prefer a real NiceGUI checkbox so Python can set checked/indeterminate
    # reliably (custom Vue bindings on QTable slots often stay empty).
    # Quasar already wraps this slot in <q-th>, so do not add another one.
    with table.add_slot("header-selection"):
        select_all_checkbox = (
            ui.checkbox(value=False, on_change=lambda _: on_select_all_header())
            .props("color=primary size=md dense")
            .classes("q-ma-none")
        )
    table.add_slot(
        "body-selection",
        """
        <div class="row justify-center items-center" style="width:100%;">
          <q-checkbox
            color="primary"
            size="md"
            :model-value="props.selected"
            @update:model-value="(val, evt) => {
              Object.getOwnPropertyDescriptor(props, 'selected').set(val, evt)
            }"
          />
        </div>
        """,
    )
    table.add_slot(
        "body-cell-image",
        """
        <q-td :props="props">
          <img v-if="props.row.image_url" :src="props.row.image_url" loading="lazy"
            style="width:64px;height:64px;object-fit:cover;border-radius:12px;display:block;margin:0 auto;" />
          <q-icon v-else name="image" size="28px" class="text-grey-5" />
        </q-td>
        """,
    )
    table.add_slot(
        "body-cell-actions",
        """
        <q-td :props="props">
          <q-btn dense flat round icon="edit" color="primary"
            @click="$parent.$emit('edit_product', props.row)" />
          <q-btn dense flat round icon="delete" color="negative"
            @click="$parent.$emit('delete_product', props.row)" />
        </q-td>
        """,
    )
    table.on("edit_product", lambda event: on_open_edit(event.args))
    table.on("delete_product", lambda event: on_open_delete(event.args))
    add_table_empty_state(table, t("products.empty.no_products"), icon="📦")

    refresh_table()
