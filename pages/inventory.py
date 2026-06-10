from __future__ import annotations

from typing import Any

from nicegui import ui
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from database import SessionLocal, engine
from models import Inventory, Product, ProductAlias, ProductCategory, StockMovement
from pages.layout import with_master_layout


def ensure_inventory_trigger() -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TRIGGER IF NOT EXISTS trg_products_create_inventory
                AFTER INSERT ON products
                BEGIN
                    INSERT OR IGNORE INTO inventory (product_id, quantity, updated_at)
                    VALUES (NEW.id, 0, CURRENT_TIMESTAMP);
                END
                """
            )
        )


def ensure_inventory_rows() -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT OR IGNORE INTO inventory (product_id, quantity, updated_at)
                SELECT p.id, 0, CURRENT_TIMESTAMP
                FROM products p
                """
            )
        )


def get_stock_status(quantity: int, min_stock: int) -> tuple[str, str]:
    if quantity <= 0:
        return "Out Of Stock", "negative"
    if quantity <= max(min_stock, 0):
        return "Low Stock", "warning"
    return "In Stock", "positive"


def load_filter_options() -> dict[str, dict[str, str]]:
    with SessionLocal() as session:
        categories = session.scalars(
            select(ProductCategory).order_by(func.lower(ProductCategory.name).asc())
        ).all()
        sizes = session.scalars(
            select(Product.size)
            .where(Product.size.is_not(None))
            .where(func.trim(Product.size) != "")
            .distinct()
            .order_by(Product.size.asc())
        ).all()
        pressures = session.scalars(
            select(Product.pressure)
            .where(Product.pressure.is_not(None))
            .where(func.trim(Product.pressure) != "")
            .distinct()
            .order_by(Product.pressure.asc())
        ).all()

    return {
        "categories": {"": "All", **{str(item.id): item.name for item in categories}},
        "sizes": {"": "All", **{value: value for value in sizes if value}},
        "pressures": {"": "All", **{value: value for value in pressures if value}},
        "stock_statuses": {
            "": "All",
            "in_stock": "In Stock",
            "low_stock": "Low Stock",
            "out_of_stock": "Out Of Stock",
        },
    }


def load_inventory_rows(filters: dict[str, str]) -> list[dict[str, Any]]:
    ensure_inventory_rows()
    with SessionLocal() as session:
        stmt = (
            select(Product)
            .options(selectinload(Product.product_category), selectinload(Product.inventory))
            .order_by(Product.name.asc())
        )
        if filters["search"].strip():
            term = f'%{filters["search"].strip()}%'
            alias_product_ids = select(ProductAlias.product_id).where(
                ProductAlias.alias.ilike(term)
            )
            stmt = stmt.where(or_(Product.name.ilike(term), Product.id.in_(alias_product_ids)))
        if filters["category_id"].strip():
            stmt = stmt.where(Product.category_id == int(filters["category_id"]))
        if filters["size"].strip():
            stmt = stmt.where(Product.size == filters["size"])
        if filters["pressure"].strip():
            stmt = stmt.where(Product.pressure == filters["pressure"])

        products = session.scalars(stmt).all()

        rows: list[dict[str, Any]] = []
        for product in products:
            quantity = product.inventory.quantity if product.inventory is not None else 0
            status, status_color = get_stock_status(quantity=quantity, min_stock=product.min_stock)
            if filters["stock_status"] == "in_stock" and status != "In Stock":
                continue
            if filters["stock_status"] == "low_stock" and status != "Low Stock":
                continue
            if filters["stock_status"] == "out_of_stock" and status != "Out Of Stock":
                continue

            rows.append(
                {
                    "product_id": product.id,
                    "product_name": product.name,
                    "category": (
                        product.product_category.name
                        if product.product_category is not None
                        else (product.category or "")
                    ),
                    "size": product.size or "",
                    "pressure": product.pressure or "",
                    "material": product.material or "",
                    "unit": product.unit,
                    "quantity": quantity,
                    "min_stock": product.min_stock,
                    "status": status,
                    "status_color": status_color,
                }
            )
        return rows


def load_stock_movement_rows(product_id: int) -> list[dict[str, Any]]:
    with SessionLocal() as session:
        movements = session.scalars(
            select(StockMovement)
            .where(StockMovement.product_id == product_id)
            .order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
        ).all()

    return [
        {
            "id": movement.id,
            "date": movement.created_at.strftime("%Y-%m-%d %H:%M:%S")
            if movement.created_at
            else "",
            "movement_type": movement.movement_type,
            "quantity": movement.quantity,
            "reference_type": movement.reference_type or "",
            "notes": movement.notes or "",
        }
        for movement in movements
    ]


def get_dashboard_stats(rows: list[dict[str, Any]]) -> dict[str, int]:
    total_products = len(rows)
    total_quantity = sum(int(row["quantity"]) for row in rows)
    low_stock_count = sum(1 for row in rows if row["status"] == "Low Stock")
    out_of_stock_count = sum(1 for row in rows if row["status"] == "Out Of Stock")
    return {
        "total_products": total_products,
        "total_quantity": total_quantity,
        "low_stock_count": low_stock_count,
        "out_of_stock_count": out_of_stock_count,
    }


def adjust_stock(
    *,
    product_id: int,
    quantity: int,
    movement_type: str,
    notes: str | None = None,
) -> None:
    if quantity <= 0:
        raise ValueError("Quantity must be greater than zero.")
    if movement_type not in {"IN", "OUT"}:
        raise ValueError("Invalid movement type.")

    with SessionLocal.begin() as session:
        product = session.get(Product, product_id)
        if product is None:
            raise ValueError("Product not found.")

        inventory = session.get(Inventory, product_id)
        if inventory is None:
            inventory = Inventory(product_id=product_id, quantity=0)
            session.add(inventory)
            session.flush()

        if movement_type == "OUT" and inventory.quantity - quantity < 0:
            raise ValueError("Quantity cannot become negative.")

        if movement_type == "IN":
            inventory.quantity += quantity
        else:
            inventory.quantity -= quantity

        movement = StockMovement(
            product_id=product_id,
            movement_type=movement_type,
            quantity=quantity,
            reference_type="MANUAL",
            reference_id=product_id,
            notes=(notes or "").strip() or None,
        )
        session.add(movement)


@ui.page("/inventory")
@with_master_layout("Inventory")
def inventory_page() -> None:
    ensure_inventory_trigger()
    ensure_inventory_rows()

    filters = {
        "search": "",
        "category_id": "",
        "size": "",
        "pressure": "",
        "stock_status": "",
    }

    ui.label("Inventory").classes("text-h4 q-mb-md")

    stat_total_products: Any = None
    stat_total_quantity: Any = None
    stat_low_stock: Any = None
    stat_out_of_stock: Any = None

    table_columns = [
        {"name": "product_name", "label": "Product Name", "field": "product_name", "align": "left"},
        {"name": "quantity", "label": "Quantity", "field": "quantity", "align": "right"},
        {"name": "status", "label": "Status", "field": "status", "align": "center"},
        {"name": "category", "label": "Category", "field": "category", "align": "left"},
        {"name": "size", "label": "Size", "field": "size", "align": "left"},
        {"name": "pressure", "label": "Pressure", "field": "pressure", "align": "left"},
        {"name": "material", "label": "Material", "field": "material", "align": "left"},
        {"name": "unit", "label": "Unit", "field": "unit", "align": "left"},
        {"name": "min_stock", "label": "Minimum Stock", "field": "min_stock", "align": "right"},
        {"name": "actions", "label": "Actions", "field": "actions", "align": "center"},
    ]
    inventory_table: Any = None

    filter_options = load_filter_options()
    category_options = filter_options["categories"]
    size_options = filter_options["sizes"]
    pressure_options = filter_options["pressures"]
    stock_status_options = filter_options["stock_statuses"]

    category_select: Any = None
    size_select: Any = None
    pressure_select: Any = None
    status_select: Any = None
    search_input: Any = None

    def refresh_page() -> None:
        nonlocal category_options, size_options, pressure_options, stock_status_options
        try:
            latest_options = load_filter_options()
            category_options = latest_options["categories"]
            size_options = latest_options["sizes"]
            pressure_options = latest_options["pressures"]
            stock_status_options = latest_options["stock_statuses"]

            if category_select is not None:
                category_select.options = category_options
                category_select.update()
            if size_select is not None:
                size_select.options = size_options
                size_select.update()
            if pressure_select is not None:
                pressure_select.options = pressure_options
                pressure_select.update()
            if status_select is not None:
                status_select.options = stock_status_options
                status_select.update()

            if inventory_table is None:
                return

            rows = load_inventory_rows(filters)
            inventory_table.rows = rows
            inventory_table.update()

            stats = get_dashboard_stats(rows)
            stat_total_products.text = str(stats["total_products"])
            stat_total_quantity.text = str(stats["total_quantity"])
            stat_low_stock.text = str(stats["low_stock_count"])
            stat_out_of_stock.text = str(stats["out_of_stock_count"])
        except SQLAlchemyError:
            ui.notify("Failed to load inventory.", color="negative")

    add_stock_target: dict[str, Any] | None = None
    remove_stock_target: dict[str, Any] | None = None

    with ui.dialog() as add_stock_dialog, ui.card().classes("w-[450px] max-w-full"):
        ui.label("Add Stock").classes("text-h6")
        add_product_name_label = ui.label("").classes("text-subtitle1")
        add_current_qty_label = ui.label("").classes("text-caption text-grey-8")
        add_quantity_input = ui.number("Quantity To Add", value=1, min=1, precision=0).classes("w-full")
        add_notes_input = ui.textarea("Reason").classes("w-full")
        with ui.row().classes("justify-end w-full q-mt-sm"):
            ui.button("Cancel", on_click=add_stock_dialog.close, color="grey-6")

            def submit_add_stock() -> None:
                nonlocal add_stock_target
                if add_stock_target is None:
                    return
                try:
                    adjust_stock(
                        product_id=int(add_stock_target["product_id"]),
                        quantity=int(add_quantity_input.value or 0),
                        movement_type="IN",
                        notes=str(add_notes_input.value or ""),
                    )
                    ui.notify("Stock added successfully.", color="positive")
                    add_stock_dialog.close()
                    refresh_page()
                except ValueError as exc:
                    ui.notify(str(exc), color="warning")
                except SQLAlchemyError:
                    ui.notify("Failed to add stock.", color="negative")

            ui.button("Save", on_click=submit_add_stock, color="primary")

    with ui.dialog() as remove_stock_dialog, ui.card().classes("w-[450px] max-w-full"):
        ui.label("Remove Stock").classes("text-h6")
        remove_product_name_label = ui.label("").classes("text-subtitle1")
        remove_current_qty_label = ui.label("").classes("text-caption text-grey-8")
        remove_quantity_input = ui.number("Quantity To Remove", value=1, min=1, precision=0).classes("w-full")
        remove_notes_input = ui.textarea("Reason").classes("w-full")
        with ui.row().classes("justify-end w-full q-mt-sm"):
            ui.button("Cancel", on_click=remove_stock_dialog.close, color="grey-6")

            def submit_remove_stock() -> None:
                nonlocal remove_stock_target
                if remove_stock_target is None:
                    return
                try:
                    adjust_stock(
                        product_id=int(remove_stock_target["product_id"]),
                        quantity=int(remove_quantity_input.value or 0),
                        movement_type="OUT",
                        notes=str(remove_notes_input.value or ""),
                    )
                    ui.notify("Stock removed successfully.", color="positive")
                    remove_stock_dialog.close()
                    refresh_page()
                except ValueError as exc:
                    ui.notify(str(exc), color="warning")
                except SQLAlchemyError:
                    ui.notify("Failed to remove stock.", color="negative")

            ui.button("Save", on_click=submit_remove_stock, color="primary")

    with ui.row().classes("w-full q-mb-md justify-center"):
        with ui.row().classes("w-full max-w-3xl items-end justify-center gap-2"):
            search_input = ui.input(
                label="Search Product / Alias",
                placeholder="Search by product name or alias",
                on_change=lambda e: filters.__setitem__("search", e.value or ""),
            ).classes("w-full max-w-2xl")
            ui.button("Search", on_click=refresh_page, icon="search")

    with ui.card().classes("w-full q-pa-md"):
        with ui.row().classes("w-full items-start gap-4 no-wrap"):
            with ui.column().classes("w-[280px] min-w-[250px] max-w-[300px]"):
                ui.label("Filters").classes("text-subtitle1 q-mb-sm")
                category_select = ui.select(
                    options=category_options,
                    label="Category",
                    value="",
                    on_change=lambda e: filters.__setitem__("category_id", e.value or ""),
                    with_input=True,
                ).classes("w-full q-mb-sm")
                size_select = ui.select(
                    options=size_options,
                    label="Size",
                    value="",
                    on_change=lambda e: filters.__setitem__("size", e.value or ""),
                    with_input=True,
                ).classes("w-full q-mb-sm")
                pressure_select = ui.select(
                    options=pressure_options,
                    label="Pressure",
                    value="",
                    on_change=lambda e: filters.__setitem__("pressure", e.value or ""),
                    with_input=True,
                ).classes("w-full q-mb-sm")
                status_select = ui.select(
                    options=stock_status_options,
                    label="Stock Status",
                    value="",
                    on_change=lambda e: filters.__setitem__("stock_status", e.value or ""),
                ).classes("w-full q-mb-md")

                def reset_filters() -> None:
                    filters["search"] = ""
                    filters["category_id"] = ""
                    filters["size"] = ""
                    filters["pressure"] = ""
                    filters["stock_status"] = ""
                    search_input.value = ""
                    category_select.value = ""
                    size_select.value = ""
                    pressure_select.value = ""
                    status_select.value = ""
                    search_input.update()
                    category_select.update()
                    size_select.update()
                    pressure_select.update()
                    status_select.update()
                    refresh_page()

                ui.button("Apply Filters", on_click=refresh_page, icon="filter_alt").classes("w-full")
                ui.button("Reset Filters", on_click=reset_filters, icon="refresh").classes("w-full q-mt-sm")

            with ui.column().classes("flex-1 min-w-0"):
                with ui.element("div").classes("w-full overflow-auto").style("max-height: calc(100vh - 360px);"):
                    inventory_table = ui.table(
                        columns=table_columns,
                        rows=[],
                        row_key="product_id",
                        pagination=15,
                    ).classes("w-full")

    with ui.row().classes("w-full items-stretch q-gutter-sm q-mt-md q-mb-md"):
        with ui.card().classes("flex-1 min-w-[180px] q-pa-md"):
            stat_total_products = ui.label("0").classes("text-h4 text-weight-bold text-center")
            ui.label("Total Products").classes("text-subtitle2 text-grey-8 text-center")
        with ui.card().classes("flex-1 min-w-[180px] q-pa-md"):
            stat_total_quantity = ui.label("0").classes("text-h4 text-weight-bold text-center")
            ui.label("Total Quantity").classes("text-subtitle2 text-grey-8 text-center")
        with ui.card().classes("flex-1 min-w-[180px] q-pa-md"):
            stat_low_stock = ui.label("0").classes("text-h4 text-weight-bold text-center")
            ui.label("Low Stock Count").classes("text-subtitle2 text-grey-8 text-center")
        with ui.card().classes("flex-1 min-w-[180px] q-pa-md"):
            stat_out_of_stock = ui.label("0").classes("text-h4 text-weight-bold text-center")
            ui.label("Out Of Stock Count").classes("text-subtitle2 text-grey-8 text-center")

    inventory_table.add_slot(
        "body-cell-status",
        """
        <q-td :props="props">
          <q-badge :color="props.row.status_color" :label="props.row.status" />
        </q-td>
        """,
    )
    inventory_table.add_slot(
        "body-cell-actions",
        """
        <q-td :props="props">
          <q-btn dense flat round icon="add" color="positive"
            @click="$parent.$emit('add_stock', props.row)" />
          <q-btn dense flat round icon="remove" color="negative"
            @click="$parent.$emit('remove_stock', props.row)" />
          <q-btn dense flat round icon="history" color="primary"
            @click="$parent.$emit('history_stock', props.row)" />
        </q-td>
        """,
    )
    inventory_table.add_slot(
        "header-cell-min_stock",
        """
        <q-th :props="props">
          Minimum Stock
          <q-icon name="info" size="16px" class="q-ml-xs text-grey-7">
            <q-tooltip>
              When quantity falls below this value, product is considered Low Stock.
            </q-tooltip>
          </q-icon>
        </q-th>
        """,
    )

    with ui.dialog() as history_dialog, ui.card().classes("w-[900px] max-w-full"):
        history_title = ui.label("Stock Movement History").classes("text-h6")
        history_columns = [
            {"name": "date", "label": "Date", "field": "date", "align": "left"},
            {"name": "movement_type", "label": "Movement Type", "field": "movement_type", "align": "left"},
            {"name": "quantity", "label": "Quantity", "field": "quantity", "align": "right"},
            {"name": "reference_type", "label": "Reference Type", "field": "reference_type", "align": "left"},
            {"name": "notes", "label": "Notes", "field": "notes", "align": "left"},
        ]
        history_table = ui.table(columns=history_columns, rows=[], row_key="id", pagination=10).classes("w-full")
        with ui.row().classes("justify-end w-full q-mt-md"):
            ui.button("Close", on_click=history_dialog.close, color="grey-6")

    def open_add_stock(row: dict[str, Any]) -> None:
        nonlocal add_stock_target
        add_stock_target = row
        add_product_name_label.text = f'Product Name: {row["product_name"]}'
        add_current_qty_label.text = f'Current Quantity: {row["quantity"]}'
        add_quantity_input.value = 1
        add_notes_input.value = ""
        add_stock_dialog.open()

    def open_remove_stock(row: dict[str, Any]) -> None:
        nonlocal remove_stock_target
        remove_stock_target = row
        remove_product_name_label.text = f'Product Name: {row["product_name"]}'
        remove_current_qty_label.text = f'Current Quantity: {row["quantity"]}'
        remove_quantity_input.value = 1
        remove_notes_input.value = ""
        remove_stock_dialog.open()

    def open_history(row: dict[str, Any]) -> None:
        history_title.text = f'Stock Movement History: {row["product_name"]}'
        history_table.rows = load_stock_movement_rows(int(row["product_id"]))
        history_table.update()
        history_dialog.open()

    inventory_table.on("add_stock", lambda e: open_add_stock(e.args))
    inventory_table.on("remove_stock", lambda e: open_remove_stock(e.args))
    inventory_table.on("history_stock", lambda e: open_history(e.args))

    refresh_page()