from __future__ import annotations

from typing import Any

from nicegui import ui
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from core.i18n import movement_type_label, stock_status_label, t
from database import SessionLocal, engine
from models import Inventory, Product, ProductAlias, ProductCategory, StockMovement
from pages.components import (
    add_table_empty_state,
    data_table_card,
    filter_sidebar,
    page_header,
    search_panel,
    statistic_card,
    statistic_grid,
    style_status_column,
)
from pages.layout import with_master_layout

_STOCK_STATUS_ENGLISH: dict[str, str] = {
    "in_stock": "In Stock",
    "low_stock": "Low Stock",
    "out_of_stock": "Out Of Stock",
}


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


def get_stock_status(quantity: int, min_stock: int) -> tuple[str, str, str]:
    if quantity <= 0:
        status_code = "out_of_stock"
        color = "negative"
    elif quantity <= max(min_stock, 0):
        status_code = "low_stock"
        color = "warning"
    else:
        status_code = "in_stock"
        color = "positive"
    return status_code, stock_status_label(_STOCK_STATUS_ENGLISH[status_code]), color


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

    all_label = t("common.filter.all")
    return {
        "categories": {"": all_label, **{str(item.id): item.name for item in categories}},
        "sizes": {"": all_label, **{value: value for value in sizes if value}},
        "pressures": {"": all_label, **{value: value for value in pressures if value}},
        "stock_statuses": {
            "": all_label,
            "in_stock": stock_status_label("In Stock"),
            "low_stock": stock_status_label("Low Stock"),
            "out_of_stock": stock_status_label("Out Of Stock"),
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
            status_code, display_label, status_color = get_stock_status(
                quantity=quantity, min_stock=product.min_stock
            )
            if filters["stock_status"] == "in_stock" and status_code != "in_stock":
                continue
            if filters["stock_status"] == "low_stock" and status_code != "low_stock":
                continue
            if filters["stock_status"] == "out_of_stock" and status_code != "out_of_stock":
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
                    "status": display_label,
                    "status_code": status_code,
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
            "movement_type": movement_type_label(movement.movement_type),
            "quantity": movement.quantity,
            "reference_type": movement.reference_type or "",
            "notes": movement.notes or "",
        }
        for movement in movements
    ]


def get_dashboard_stats(rows: list[dict[str, Any]]) -> dict[str, int]:
    total_products = len(rows)
    total_quantity = sum(int(row["quantity"]) for row in rows)
    low_stock_count = sum(1 for row in rows if row["status_code"] == "low_stock")
    out_of_stock_count = sum(1 for row in rows if row["status_code"] == "out_of_stock")
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
        raise ValueError(t("inventory.error.quantity_must_be_positive"))
    if movement_type not in {"IN", "OUT"}:
        raise ValueError(t("inventory.error.invalid_movement_type"))

    with SessionLocal.begin() as session:
        product = session.get(Product, product_id)
        if product is None:
            raise ValueError(t("inventory.error.product_not_found"))

        inventory = session.get(Inventory, product_id)
        if inventory is None:
            inventory = Inventory(product_id=product_id, quantity=0)
            session.add(inventory)
            session.flush()

        if movement_type == "OUT" and inventory.quantity - quantity < 0:
            raise ValueError(t("inventory.error.quantity_cannot_be_negative"))

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
@with_master_layout(t("inventory.title"))
def inventory_page() -> None:
    ensure_inventory_rows()

    filters = {
        "search": "",
        "category_id": "",
        "size": "",
        "pressure": "",
        "stock_status": "",
    }

    page_header(t("inventory.title"), t("inventory.description"))

    stat_total_products: Any = None
    stat_total_quantity: Any = None
    stat_low_stock: Any = None
    stat_out_of_stock: Any = None

    table_columns = [
        {
            "name": "product_name",
            "label": t("inventory.table.product_name"),
            "field": "product_name",
            "align": "left",
        },
        {
            "name": "quantity",
            "label": t("common.table.quantity"),
            "field": "quantity",
            "align": "right",
        },
        {
            "name": "status",
            "label": t("common.table.status"),
            "field": "status",
            "align": "center",
        },
        {
            "name": "category",
            "label": t("inventory.table.category"),
            "field": "category",
            "align": "left",
        },
        {
            "name": "size",
            "label": t("inventory.filter.size"),
            "field": "size",
            "align": "left",
        },
        {
            "name": "pressure",
            "label": t("inventory.filter.pressure"),
            "field": "pressure",
            "align": "left",
        },
        {
            "name": "material",
            "label": t("inventory.table.material"),
            "field": "material",
            "align": "left",
        },
        {
            "name": "unit",
            "label": t("inventory.table.unit"),
            "field": "unit",
            "align": "left",
        },
        {
            "name": "min_stock",
            "label": t("inventory.table.minimum_stock"),
            "field": "min_stock",
            "align": "right",
        },
        {
            "name": "actions",
            "label": t("common.table.actions"),
            "field": "actions",
            "align": "center",
        },
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
            ui.notify(t("inventory.notify.load_failed"), color="negative")

    add_stock_target: dict[str, Any] | None = None
    remove_stock_target: dict[str, Any] | None = None

    with ui.dialog() as add_stock_dialog, ui.card().classes("w-[450px] max-w-full"):
        ui.label(t("inventory.dialog.add_stock")).classes("text-h6")
        add_product_name_label = ui.label("").classes("text-subtitle1")
        add_current_qty_label = ui.label("").classes("text-caption text-grey-8")
        add_quantity_input = ui.number(
            t("inventory.dialog.quantity_to_add"), value=1, min=1, precision=0
        ).classes("w-full")
        add_notes_input = ui.textarea(t("inventory.dialog.reason")).classes("w-full")
        with ui.row().classes("justify-end w-full q-mt-sm"):
            ui.button(t("common.button.cancel"), on_click=add_stock_dialog.close, color="grey-6")

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
                    ui.notify(t("inventory.notify.stock_added"), color="positive")
                    add_stock_dialog.close()
                    refresh_page()
                except ValueError as exc:
                    ui.notify(str(exc), color="warning")
                except SQLAlchemyError:
                    ui.notify(t("inventory.notify.add_stock_failed"), color="negative")

            ui.button(t("common.button.save"), on_click=submit_add_stock, color="primary")

    with ui.dialog() as remove_stock_dialog, ui.card().classes("w-[450px] max-w-full"):
        ui.label(t("inventory.dialog.remove_stock")).classes("text-h6")
        remove_product_name_label = ui.label("").classes("text-subtitle1")
        remove_current_qty_label = ui.label("").classes("text-caption text-grey-8")
        remove_quantity_input = ui.number(
            t("inventory.dialog.quantity_to_remove"), value=1, min=1, precision=0
        ).classes("w-full")
        remove_notes_input = ui.textarea(t("inventory.dialog.reason")).classes("w-full")
        with ui.row().classes("justify-end w-full q-mt-sm"):
            ui.button(t("common.button.cancel"), on_click=remove_stock_dialog.close, color="grey-6")

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
                    ui.notify(t("inventory.notify.stock_removed"), color="positive")
                    remove_stock_dialog.close()
                    refresh_page()
                except ValueError as exc:
                    ui.notify(str(exc), color="warning")
                except SQLAlchemyError:
                    ui.notify(t("inventory.notify.remove_stock_failed"), color="negative")

            ui.button(t("common.button.save"), on_click=submit_remove_stock, color="primary")

    with search_panel():
        with ui.row().classes("w-full items-end no-wrap gap-3"):
            search_input = ui.input(
                label=t("inventory.search.label"),
                placeholder=t("inventory.search.placeholder"),
                on_change=lambda e: filters.__setitem__("search", e.value or ""),
            ).classes("flex-1 min-w-0")
            ui.button(t("common.button.search"), on_click=refresh_page, icon="search")

    with ui.row().classes("w-full items-start gap-4 no-wrap"):
        with filter_sidebar():
                category_select = ui.select(
                    options=category_options,
                    label=t("inventory.filter.category"),
                    value="",
                    on_change=lambda e: filters.__setitem__("category_id", e.value or ""),
                    with_input=True,
                ).classes("w-full q-mb-sm")
                size_select = ui.select(
                    options=size_options,
                    label=t("inventory.filter.size"),
                    value="",
                    on_change=lambda e: filters.__setitem__("size", e.value or ""),
                    with_input=True,
                ).classes("w-full q-mb-sm")
                pressure_select = ui.select(
                    options=pressure_options,
                    label=t("inventory.filter.pressure"),
                    value="",
                    on_change=lambda e: filters.__setitem__("pressure", e.value or ""),
                    with_input=True,
                ).classes("w-full q-mb-sm")
                status_select = ui.select(
                    options=stock_status_options,
                    label=t("inventory.filter.stock_status"),
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

                ui.button(
                    t("common.button.apply_filters"), on_click=refresh_page, icon="filter_alt"
                ).classes("w-full")
                ui.button(
                    t("common.button.reset_filters"), on_click=reset_filters, icon="refresh"
                ).classes("w-full q-mt-sm")

        with data_table_card().classes("flex-1 min-w-0"):
            with ui.element("div").classes("w-full overflow-auto").style("max-height: calc(100vh - 360px);"):
                inventory_table = ui.table(
                    columns=table_columns,
                    rows=[],
                    row_key="product_id",
                    pagination=15,
                ).classes("w-full")

    with statistic_grid().classes("q-mt-md"):
        stat_total_products = statistic_card(t("inventory.stat.total_products"), icon="category")
        stat_total_quantity = statistic_card(t("inventory.stat.total_quantity"), icon="inventory_2")
        stat_low_stock = statistic_card(t("inventory.stat.low_stock_count"), icon="report_problem")
        stat_out_of_stock = statistic_card(
            t("inventory.stat.out_of_stock_count"), icon="remove_shopping_cart"
        )

    style_status_column(inventory_table, "status")
    add_table_empty_state(inventory_table, t("inventory.empty.no_data"), icon="📦")
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
        f"""
        <q-th :props="props">
          {t("inventory.table.minimum_stock")}
          <q-icon name="info" size="16px" class="q-ml-xs text-grey-7">
            <q-tooltip>
              {t("inventory.table.minimum_stock_tooltip")}
            </q-tooltip>
          </q-icon>
        </q-th>
        """,
    )

    with ui.dialog() as history_dialog, ui.card().classes("w-[900px] max-w-full"):
        history_title = ui.label(t("inventory.dialog.history_title")).classes("text-h6")
        history_columns = [
            {
                "name": "date",
                "label": t("common.table.date"),
                "field": "date",
                "align": "left",
            },
            {
                "name": "movement_type",
                "label": t("inventory.table.movement_type"),
                "field": "movement_type",
                "align": "left",
            },
            {
                "name": "quantity",
                "label": t("common.table.quantity"),
                "field": "quantity",
                "align": "right",
            },
            {
                "name": "reference_type",
                "label": t("inventory.table.reference_type"),
                "field": "reference_type",
                "align": "left",
            },
            {
                "name": "notes",
                "label": t("common.table.notes"),
                "field": "notes",
                "align": "left",
            },
        ]
        history_table = ui.table(columns=history_columns, rows=[], row_key="id", pagination=10).classes("w-full")
        with ui.row().classes("justify-end w-full q-mt-md"):
            ui.button(t("common.button.close"), on_click=history_dialog.close, color="grey-6")

    def open_add_stock(row: dict[str, Any]) -> None:
        nonlocal add_stock_target
        add_stock_target = row
        add_product_name_label.text = t("inventory.dialog.product_name", name=row["product_name"])
        add_current_qty_label.text = t(
            "inventory.dialog.current_quantity", quantity=row["quantity"]
        )
        add_quantity_input.value = 1
        add_notes_input.value = ""
        add_stock_dialog.open()

    def open_remove_stock(row: dict[str, Any]) -> None:
        nonlocal remove_stock_target
        remove_stock_target = row
        remove_product_name_label.text = t("inventory.dialog.product_name", name=row["product_name"])
        remove_current_qty_label.text = t(
            "inventory.dialog.current_quantity", quantity=row["quantity"]
        )
        remove_quantity_input.value = 1
        remove_notes_input.value = ""
        remove_stock_dialog.open()

    def open_history(row: dict[str, Any]) -> None:
        history_title.text = t("inventory.dialog.history_title_product", name=row["product_name"])
        history_table.rows = load_stock_movement_rows(int(row["product_id"]))
        history_table.update()
        history_dialog.open()

    inventory_table.on("add_stock", lambda e: open_add_stock(e.args))
    inventory_table.on("remove_stock", lambda e: open_remove_stock(e.args))
    inventory_table.on("history_stock", lambda e: open_history(e.args))

    refresh_page()
