from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from nicegui import ui
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from database import SessionLocal
from models import Product, ProductCategory


OTHER_CATEGORY_OPTION = "other"


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"))
    try:
        return Decimal(str(value).strip()).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, AttributeError) as exc:
        raise ValueError("current_price must be a valid number") from exc


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
            .options(selectinload(Product.product_category))
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
        return [
            {
                "id": product.id,
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
            for product in products
        ]


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
        raise ValueError("Category name cannot be empty.")
    if len(cleaned_name) < 2:
        raise ValueError("Category name must be at least 2 characters.")

    if find_category_by_name(cleaned_name) is not None:
        raise ValueError("Category already exists.")

    with SessionLocal() as session:
        category = ProductCategory(name=cleaned_name)
        session.add(category)
        session.commit()
        session.refresh(category)
        return category


def create_product(data: dict[str, Any]) -> Product:
    name = str(data.get("name", "")).strip()
    if not name:
        raise ValueError("name is required")

    unit = str(data.get("unit", "pcs")).strip() or "pcs"
    try:
        min_stock = int(data.get("min_stock", 0) or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("min_stock must be an integer") from exc
    if min_stock < 0:
        raise ValueError("min_stock cannot be negative")

    with SessionLocal() as session:
        raw_category_id = str(data.get("category_id", "")).strip()
        if raw_category_id == OTHER_CATEGORY_OPTION:
            raise ValueError("Please create and select a valid category.")
        try:
            category_id = int(raw_category_id) if raw_category_id else None
        except ValueError as exc:
            raise ValueError("Please select a valid category.") from exc
        category_name: str | None = None
        if category_id is not None:
            category = session.get(ProductCategory, category_id)
            if category is None:
                raise ValueError("Please select a valid category")
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
        raise ValueError("name is required")

    try:
        min_stock = int(data.get("min_stock", 0) or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("min_stock must be an integer") from exc
    if min_stock < 0:
        raise ValueError("min_stock cannot be negative")

    with SessionLocal() as session:
        product = session.get(Product, product_id)
        if product is None:
            return False

        raw_category_id = str(data.get("category_id", "")).strip()
        if raw_category_id == OTHER_CATEGORY_OPTION:
            raise ValueError("Please create and select a valid category.")
        try:
            category_id = int(raw_category_id) if raw_category_id else None
        except ValueError as exc:
            raise ValueError("Please select a valid category.") from exc
        category_name: str | None = None
        if category_id is not None:
            category = session.get(ProductCategory, category_id)
            if category is None:
                raise ValueError("Please select a valid category")
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
def products_page() -> None:
    ui.label("Products").classes("text-h4 q-mb-md")

    filters = {
        "name": "",
        "category_id": "",
        "size": "",
        "pressure": "",
        "stock_status": "",
    }
    selected_row: dict[str, Any] | None = None
    editing_product_id: int | None = None

    columns = [
        {"name": "name", "label": "Name", "field": "name", "align": "left"},
        {"name": "category", "label": "Category", "field": "category", "align": "left"},
        {"name": "size", "label": "Size", "field": "size", "align": "left"},
        {"name": "pressure", "label": "Pressure", "field": "pressure", "align": "left"},
        {"name": "material", "label": "Material", "field": "material", "align": "left"},
        {"name": "unit", "label": "Unit", "field": "unit", "align": "left"},
        {
            "name": "current_price",
            "label": "Current Price",
            "field": "current_price",
            "align": "right",
        },
        {"name": "min_stock", "label": "Min Stock", "field": "min_stock", "align": "right"},
        {"name": "description", "label": "Description", "field": "description", "align": "left"},
        {"name": "actions", "label": "Actions", "field": "actions", "align": "center"},
    ]

    table: Any = None
    category_filter_options: dict[str, str] = {"": "All"}
    category_form_options: dict[str, str] = {"": "Select category", OTHER_CATEGORY_OPTION: "➕ Other..."}
    size_filter_options: dict[str, str] = {"": "All"}
    pressure_filter_options: dict[str, str] = {"": "All"}
    stock_status_filter_options: dict[str, str] = {
        "": "All",
        "in_stock": "Normal",
        "low_stock": "Low Stock",
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
                {"": "All", **{str(category.id): category.name for category in categories}}
            )
            category_form_options.clear()
            category_form_options.update(
                {str(category.id): category.name for category in categories}
            )
            category_form_options[""] = "Select category"
            category_form_options[OTHER_CATEGORY_OPTION] = "➕ Other..."
            size_filter_options.clear()
            size_filter_options.update({"": "All", **{v: v for v in options["sizes"]}})
            pressure_filter_options.clear()
            pressure_filter_options.update({"": "All", **{v: v for v in options["pressures"]}})

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

            table.rows = load_products(
                name=filters["name"],
                category_id=filters["category_id"],
                size=filters["size"],
                pressure=filters["pressure"],
                stock_status=filters["stock_status"],
            )
            table.update()
        except SQLAlchemyError:
            ui.notify("Failed to load products.", color="negative")

    def build_form(dialog_title: str, form_target: str) -> tuple[ui.dialog, dict[str, Any]]:
        dialog = ui.dialog()
        with dialog, ui.card().classes("w-[700px] max-w-full"):
            ui.label(dialog_title).classes("text-h6")
            with ui.row().classes("w-full gap-2"):
                name_input = ui.input("Name").classes("col")
                category_input = ui.select(
                    options=category_form_options,
                    label="Category",
                    with_input=True,
                    value="",
                    on_change=lambda e: handle_category_select(
                        form_target,
                        getattr(e, "value", None),
                    ),
                ).classes("col")
            with ui.row().classes("w-full gap-2"):
                size_input = ui.input("Size").classes("col")
                pressure_input = ui.input("Pressure").classes("col")
            with ui.row().classes("w-full gap-2"):
                material_input = ui.input("Material").classes("col")
                unit_input = ui.select(
                    options={"шт": "шт", "кг": "кг", "м": "м"},
                    label="Unit",
                    value="шт",
                ).classes("col")
            with ui.row().classes("w-full gap-2"):
                current_price_input = ui.input("Current Price").classes("col")
                min_stock_input = ui.number("Min Stock", value=0, precision=0).classes(
                    "col"
                )
            description_input = ui.textarea("Description").classes("w-full")

            with ui.row().classes("justify-end w-full q-mt-md"):
                ui.button("Cancel", on_click=dialog.close, color="grey-6")
                action_button = ui.button("Save")

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
            "action_button": action_button,
        }
        return dialog, inputs

    add_dialog, add_inputs = build_form("Add Product", "add")
    edit_dialog, edit_inputs = build_form("Edit Product", "edit")

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

    def _reset_form(inputs: dict[str, Any]) -> None:
        inputs["name"].value = ""
        inputs["category"].value = ""
        inputs["size"].value = ""
        inputs["pressure"].value = ""
        inputs["material"].value = ""
        inputs["unit"].value = "шт"
        inputs["current_price"].value = "0.00"
        inputs["min_stock"].value = 0
        inputs["description"].value = ""

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

    with ui.dialog() as create_category_dialog, ui.card().classes("w-[420px] max-w-full"):
        ui.label("Create Category").classes("text-h6")
        category_name_input = ui.input("Category Name").classes("w-full")
        with ui.row().classes("justify-end w-full q-mt-sm"):
            ui.button("Cancel", on_click=create_category_dialog.close, color="grey-6")

            def validate_new_category() -> None:
                nonlocal pending_category_name
                candidate = (category_name_input.value or "").strip()
                if not candidate:
                    ui.notify("Category name cannot be empty.", color="warning")
                    return
                if len(candidate) < 2:
                    ui.notify("Category name must be at least 2 characters.", color="warning")
                    return
                if find_category_by_name(candidate) is not None:
                    ui.notify("Category already exists.", color="warning")
                    return
                pending_category_name = candidate
                confirmation_message.text = (
                    f"Create category '{candidate}' ?"
                )
                create_category_dialog.close()
                confirm_create_dialog.open()

            ui.button("Save", on_click=validate_new_category, color="primary")

    with ui.dialog() as confirm_create_dialog, ui.card().classes("w-[430px] max-w-full"):
        ui.label("Create Category").classes("text-h6")
        confirmation_message = ui.label("")
        with ui.row().classes("justify-end w-full q-mt-sm"):
            ui.button("Cancel", on_click=confirm_create_dialog.close, color="grey-6")

            def confirm_create_category() -> None:
                nonlocal pending_category_name
                try:
                    created = create_category(pending_category_name)
                except ValueError as exc:
                    ui.notify(str(exc), color="warning")
                    confirm_create_dialog.close()
                    return
                except SQLAlchemyError:
                    ui.notify("Failed to create category.", color="negative")
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
                ui.notify("Category created successfully.", color="positive")
                pending_category_name = ""
                confirm_create_dialog.close()

            ui.button("Create", on_click=confirm_create_category, color="primary")

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
        if value not in {OTHER_CATEGORY_OPTION, "➕ Other...", "Other..."}:
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
            create_product(_form_data(add_inputs))
            add_dialog.close()
            refresh_table()
            ui.notify("Product created successfully.", color="positive")
        except ValueError as exc:
            ui.notify(str(exc), color="warning")
        except SQLAlchemyError:
            ui.notify("Failed to create product.", color="negative")

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
            ui.notify("No product selected.", color="warning")
            return

        try:
            updated = update_product(editing_product_id, _form_data(edit_inputs))
            if not updated:
                ui.notify("Product not found.", color="warning")
                return
            edit_dialog.close()
            refresh_table()
            ui.notify("Product updated successfully.", color="positive")
        except ValueError as exc:
            ui.notify(str(exc), color="warning")
        except SQLAlchemyError:
            ui.notify("Failed to update product.", color="negative")

    with ui.dialog() as delete_dialog, ui.card():
        delete_message = ui.label("Delete selected product?")
        with ui.row().classes("justify-end w-full"):
            ui.button("Cancel", on_click=delete_dialog.close, color="grey-6")

            def confirm_delete() -> None:
                nonlocal selected_row
                if selected_row is None:
                    delete_dialog.close()
                    return
                try:
                    deleted = delete_product(int(selected_row["id"]))
                    if deleted:
                        ui.notify("Product deleted successfully.", color="positive")
                    else:
                        ui.notify("Product not found.", color="warning")
                    refresh_table()
                except SQLAlchemyError:
                    ui.notify("Failed to delete product.", color="negative")
                finally:
                    delete_dialog.close()
                    selected_row = None

            ui.button("Delete", on_click=confirm_delete, color="negative")

    def on_open_delete(row: dict[str, Any]) -> None:
        nonlocal selected_row
        selected_row = row
        delete_message.text = f'Delete product "{row["name"]}"?'
        delete_dialog.open()

    add_inputs["action_button"].on("click", on_add_product)
    edit_inputs["action_button"].on("click", on_update_product)

    def open_add_dialog() -> None:
        add_inputs["category"].options = category_form_options
        add_inputs["category"].update()
        _reset_form(add_inputs)
        add_dialog.open()

    with ui.row().classes("w-full items-start gap-4 no-wrap"):
        with ui.card().classes("w-[280px] min-w-[250px] max-w-[300px]"):
            ui.label("Filters").classes("text-subtitle1 q-mb-sm")
            category_select = ui.select(
                options=category_filter_options,
                label="Category",
                value="",
                on_change=lambda e: filters.__setitem__("category_id", e.value or ""),
                with_input=True,
            ).classes("w-full q-mb-sm")
            pressure_select = ui.select(
                options=pressure_filter_options,
                label="Pressure",
                value="",
                on_change=lambda e: filters.__setitem__("pressure", e.value or ""),
            ).classes("w-full q-mb-sm")
            size_select = ui.select(
                options=size_filter_options,
                label="Size",
                value="",
                on_change=lambda e: filters.__setitem__("size", e.value or ""),
            ).classes("w-full q-mb-sm")
            stock_status_select = ui.select(
                options=stock_status_filter_options,
                label="Stock Status",
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

            ui.button("Reset Filters", on_click=clear_filters, icon="refresh").classes(
                "w-full"
            )
            ui.button("Apply Filters", on_click=refresh_table, icon="filter_alt").classes(
                "w-full q-mt-sm"
            )

        with ui.column().classes("flex-1 min-w-0"):
            with ui.row().classes("w-full q-mb-md items-center justify-between"):
                with ui.row().classes("items-end gap-2 flex-1"):
                    ui.input(
                        label="Search Name",
                        placeholder="Name",
                        on_change=lambda e: filters.__setitem__("name", e.value or ""),
                    ).classes("w-full max-w-md")
                    ui.button("Search", on_click=refresh_table, icon="search")
                ui.button("Add Product", on_click=open_add_dialog, icon="add")

            table = ui.table(columns=columns, rows=[], row_key="id", pagination=10).classes(
                "w-full"
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

    refresh_table()