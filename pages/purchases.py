from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from nicegui import ui
from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from database import SessionLocal
from models import Inventory, Product, Purchase, PurchaseItem, StockMovement, Supplier
from pages.layout import with_master_layout


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"))
    try:
        return Decimal(str(value).strip()).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, AttributeError) as exc:
        raise ValueError("Invalid monetary value.") from exc


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _payment_summary(total_amount: Decimal, paid_amount: Decimal) -> tuple[Decimal, str]:
    if paid_amount >= total_amount:
        return Decimal("0.00"), "Paid"
    if paid_amount <= Decimal("0.00"):
        return total_amount, "Unpaid"
    return (total_amount - paid_amount).quantize(Decimal("0.01")), "Partially Paid"


def _parse_date(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("Purchase Date must be a valid date.") from exc


def load_supplier_options() -> dict[str, str]:
    with SessionLocal() as session:
        suppliers = session.scalars(
            select(Supplier).order_by(func.lower(Supplier.company_name).asc())
        ).all()
    return {"": "All", **{str(item.id): item.company_name for item in suppliers}}


def load_product_options() -> dict[str, str]:
    with SessionLocal() as session:
        products = session.scalars(
            select(Product).order_by(func.lower(Product.name).asc())
        ).all()
    return {str(item.id): item.name for item in products}


def generate_purchase_number(session: Any) -> str:
    latest_number = session.scalar(
        select(Purchase.purchase_number).order_by(Purchase.id.desc()).limit(1)
    )
    if latest_number and latest_number.startswith("PUR-"):
        suffix = latest_number.replace("PUR-", "").strip()
        if suffix.isdigit():
            return f"PUR-{int(suffix) + 1:06d}"
    max_id = session.scalar(select(func.max(Purchase.id))) or 0
    return f"PUR-{int(max_id) + 1:06d}"


def load_purchase_rows(filters: dict[str, str]) -> list[dict[str, Any]]:
    with SessionLocal() as session:
        stmt = (
            select(Purchase)
            .options(selectinload(Purchase.supplier), selectinload(Purchase.items))
            .order_by(Purchase.purchase_date.desc(), Purchase.id.desc())
        )
        if filters["search"].strip():
            term = f'%{filters["search"].strip()}%'
            stmt = stmt.where(
                or_(
                    Purchase.purchase_number.ilike(term),
                    Purchase.supplier.has(Supplier.company_name.ilike(term)),
                )
            )
        if filters["supplier_id"].strip():
            stmt = stmt.where(Purchase.supplier_id == int(filters["supplier_id"]))
        if filters["payment_status"].strip():
            stmt = stmt.where(Purchase.payment_status == filters["payment_status"])

        purchases = session.scalars(stmt).all()

    return [
        {
            "id": purchase.id,
            "purchase_number": purchase.purchase_number,
            "purchase_date": purchase.purchase_date.strftime("%Y-%m-%d"),
            "supplier": purchase.supplier.company_name if purchase.supplier else "",
            "items_count": len(purchase.items),
            "total_amount": f"{purchase.total_amount:.2f}",
            "paid_amount": f"{purchase.paid_amount:.2f}",
            "remaining_amount": f"{purchase.remaining_amount:.2f}",
            "payment_status": purchase.payment_status or "",
        }
        for purchase in purchases
    ]


def create_purchase_record(data: dict[str, Any]) -> str:
    supplier_id_raw = str(data.get("supplier_id", "")).strip()
    if not supplier_id_raw:
        raise ValueError("Supplier is required.")
    purchase_date_str = str(data.get("purchase_date", "")).strip()
    purchase_date = _parse_date(purchase_date_str)

    item_payloads = data.get("items", [])
    if not item_payloads:
        raise ValueError("At least one purchase item is required.")

    parsed_items: list[dict[str, Any]] = []
    total_amount = Decimal("0.00")
    for item in item_payloads:
        product_id_raw = str(item.get("product_id", "")).strip()
        if not product_id_raw:
            raise ValueError("Each item must have a selected product.")
        try:
            quantity = int(item.get("quantity", 0))
        except (TypeError, ValueError) as exc:
            raise ValueError("Quantity must be an integer.") from exc
        if quantity <= 0:
            raise ValueError("Quantity must be greater than zero.")
        purchase_price = _to_decimal(item.get("purchase_price", "0"))
        selling_price = _to_decimal(item.get("selling_price", "0"))
        if purchase_price < Decimal("0.00") or selling_price < Decimal("0.00"):
            raise ValueError("Prices cannot be negative.")

        line_total = (purchase_price * Decimal(quantity)).quantize(Decimal("0.01"))
        total_amount += line_total
        parsed_items.append(
            {
                "product_id": int(product_id_raw),
                "quantity": quantity,
                "purchase_price": purchase_price,
                "selling_price": selling_price,
                "total_price": line_total,
            }
        )
    total_amount = total_amount.quantize(Decimal("0.01"))

    paid_amount = _to_decimal(data.get("paid_amount", "0"))
    if paid_amount < Decimal("0.00"):
        raise ValueError("Paid Amount cannot be negative.")
    remaining_amount, payment_status = _payment_summary(total_amount, paid_amount)
    notes = _clean_text(data.get("notes"))

    with SessionLocal.begin() as session:
        supplier = session.get(Supplier, int(supplier_id_raw))
        if supplier is None:
            raise ValueError("Supplier not found.")

        purchase_number = generate_purchase_number(session)
        purchase = Purchase(
            purchase_number=purchase_number,
            supplier_id=supplier.id,
            purchase_date=purchase_date,
            total_amount=total_amount,
            paid_amount=paid_amount,
            remaining_amount=remaining_amount,
            payment_status=payment_status,
            notes=notes,
        )
        session.add(purchase)
        session.flush()

        for item in parsed_items:
            product = session.get(Product, int(item["product_id"]))
            if product is None:
                raise ValueError("Selected product not found.")
            purchase_item = PurchaseItem(
                purchase_id=purchase.id,
                product_id=product.id,
                quantity=int(item["quantity"]),
                purchase_price=item["purchase_price"],
                selling_price=item["selling_price"],
                total_price=item["total_price"],
            )
            session.add(purchase_item)

            inventory = session.get(Inventory, product.id)
            if inventory is None:
                inventory = Inventory(product_id=product.id, quantity=0)
                session.add(inventory)
                session.flush()
            inventory.quantity += int(item["quantity"])

            movement = StockMovement(
                product_id=product.id,
                movement_type="IN",
                quantity=int(item["quantity"]),
                reference_type="PURCHASE",
                reference_id=purchase.id,
                notes=f"Purchase {purchase.purchase_number}",
            )
            session.add(movement)

        return purchase_number


def load_purchase_detail(purchase_id: int) -> dict[str, Any] | None:
    with SessionLocal() as session:
        purchase = session.scalar(
            select(Purchase)
            .where(Purchase.id == purchase_id)
            .options(
                selectinload(Purchase.supplier),
                selectinload(Purchase.items).selectinload(PurchaseItem.product),
            )
        )
        if purchase is None:
            return None
        return {
            "purchase_number": purchase.purchase_number,
            "purchase_date": purchase.purchase_date.strftime("%Y-%m-%d"),
            "supplier": purchase.supplier.company_name if purchase.supplier else "",
            "total_amount": f"{purchase.total_amount:.2f}",
            "paid_amount": f"{purchase.paid_amount:.2f}",
            "remaining_amount": f"{purchase.remaining_amount:.2f}",
            "payment_status": purchase.payment_status or "",
            "notes": purchase.notes or "",
            "items": [
                {
                    "product_name": item.product.name if item.product else "",
                    "quantity": item.quantity,
                    "purchase_price": f"{item.purchase_price:.2f}",
                    "selling_price": f"{item.selling_price:.2f}",
                    "total_price": f"{item.total_price:.2f}",
                }
                for item in purchase.items
            ],
        }


@ui.page("/purchases")
@with_master_layout("Purchases")
def purchases_page() -> None:
    filters = {"search": "", "supplier_id": "", "payment_status": ""}
    payment_status_options = {"": "All", "Paid": "Paid", "Partially Paid": "Partially Paid", "Unpaid": "Unpaid"}
    supplier_options = load_supplier_options()
    product_options = load_product_options()

    ui.label("Purchases").classes("text-h4 q-mb-md")

    purchase_columns = [
        {"name": "purchase_number", "label": "Purchase Number", "field": "purchase_number", "align": "left"},
        {"name": "purchase_date", "label": "Purchase Date", "field": "purchase_date", "align": "left"},
        {"name": "supplier", "label": "Supplier", "field": "supplier", "align": "left"},
        {"name": "items_count", "label": "Items Count", "field": "items_count", "align": "right"},
        {"name": "total_amount", "label": "Total Amount", "field": "total_amount", "align": "right"},
        {"name": "paid_amount", "label": "Paid Amount", "field": "paid_amount", "align": "right"},
        {"name": "remaining_amount", "label": "Remaining Amount", "field": "remaining_amount", "align": "right"},
        {"name": "payment_status", "label": "Payment Status", "field": "payment_status", "align": "center"},
        {"name": "actions", "label": "Actions", "field": "actions", "align": "center"},
    ]
    purchases_table: Any = None

    search_input: Any = None
    supplier_filter_select: Any = None
    payment_status_select: Any = None

    def refresh_table() -> None:
        nonlocal supplier_options
        try:
            supplier_options = load_supplier_options()
            if supplier_filter_select is not None:
                supplier_filter_select.options = supplier_options
                supplier_filter_select.update()
            if purchases_table is None:
                return
            purchases_table.rows = load_purchase_rows(filters)
            purchases_table.update()
        except SQLAlchemyError:
            ui.notify("Failed to load purchases.", color="negative")

    with ui.dialog() as details_dialog, ui.card().classes("w-[950px] max-w-full"):
        details_title = ui.label("Purchase Details").classes("text-h6")
        info_line = ui.label("")
        totals_line = ui.label("")
        notes_line = ui.label("")
        detail_item_columns = [
            {"name": "product_name", "label": "Product", "field": "product_name", "align": "left"},
            {"name": "quantity", "label": "Quantity", "field": "quantity", "align": "right"},
            {"name": "purchase_price", "label": "Purchase Price", "field": "purchase_price", "align": "right"},
            {"name": "selling_price", "label": "Selling Price", "field": "selling_price", "align": "right"},
            {"name": "total_price", "label": "Total", "field": "total_price", "align": "right"},
        ]
        details_items_table = ui.table(
            columns=detail_item_columns,
            rows=[],
            row_key="product_name",
            pagination=10,
        ).classes("w-full")
        with ui.row().classes("justify-end w-full q-mt-sm"):
            ui.button("Close", on_click=details_dialog.close, color="grey-6")

    with ui.dialog() as add_dialog, ui.card().classes("w-[1100px] max-w-full"):
        ui.label("Add Purchase").classes("text-h6")
        with ui.row().classes("w-full gap-2"):
            add_supplier_select = ui.select(
                options={"": "Select supplier", **{key: value for key, value in supplier_options.items() if key}},
                label="Supplier",
                value="",
                with_input=True,
            ).classes("col")
            add_purchase_date_input = ui.input("Purchase Date", value=datetime.now().strftime("%Y-%m-%d")).props("type=date").classes("col")
        add_notes_input = ui.textarea("Notes").classes("w-full")

        ui.separator()
        ui.label("Items").classes("text-subtitle1")
        items_container = ui.column().classes("w-full gap-2")
        item_rows: list[dict[str, Any]] = []

        ui.separator()
        ui.label("Payment").classes("text-subtitle1")
        with ui.row().classes("w-full gap-2"):
            total_amount_display = ui.input("Total Amount", value="0.00").props("readonly").classes("col")
            paid_amount_input = ui.input("Paid Amount", value="0.00").classes("col")
        with ui.row().classes("w-full gap-2"):
            remaining_amount_display = ui.input("Remaining Amount", value="0.00").props("readonly").classes("col")
            payment_status_display = ui.input("Payment Status", value="Unpaid").props("readonly").classes("col")

        def recalc_totals() -> None:
            total = Decimal("0.00")
            for row in item_rows:
                try:
                    qty = int(row["quantity"].value or 0)
                except (TypeError, ValueError):
                    qty = 0
                try:
                    p_price = _to_decimal(row["purchase_price"].value or "0")
                except ValueError:
                    p_price = Decimal("0.00")
                line_total = (p_price * Decimal(max(qty, 0))).quantize(Decimal("0.01"))
                row["total"].value = f"{line_total:.2f}"
                row["total"].update()
                total += line_total
            total = total.quantize(Decimal("0.01"))
            try:
                paid = _to_decimal(paid_amount_input.value or "0")
            except ValueError:
                paid = Decimal("0.00")
            remaining, status = _payment_summary(total, paid)
            total_amount_display.value = f"{total:.2f}"
            remaining_amount_display.value = f"{remaining:.2f}"
            payment_status_display.value = status
            total_amount_display.update()
            remaining_amount_display.update()
            payment_status_display.update()

        def add_item_row(defaults: dict[str, Any] | None = None) -> None:
            defaults = defaults or {}
            with items_container:
                row_box = ui.row().classes("w-full items-end gap-2")
                with row_box:
                    product_select = ui.select(
                        options={"": "Select product", **product_options},
                        label="Product",
                        value=str(defaults.get("product_id", "")),
                        with_input=True,
                    ).classes("w-[260px]")
                    qty_input = ui.number("Quantity", value=defaults.get("quantity", 1), min=1, precision=0).classes("w-[120px]")
                    purchase_price_input = ui.input("Purchase Price", value=str(defaults.get("purchase_price", "0.00"))).classes("w-[160px]")
                    selling_price_input = ui.input("Selling Price", value=str(defaults.get("selling_price", "0.00"))).classes("w-[160px]")
                    total_input = ui.input("Total", value="0.00").props("readonly").classes("w-[140px]")
                    remove_btn = ui.button("Remove Item", color="negative")
            row_data = {
                "container": row_box,
                "product": product_select,
                "quantity": qty_input,
                "purchase_price": purchase_price_input,
                "selling_price": selling_price_input,
                "total": total_input,
            }
            item_rows.append(row_data)

            def remove_row() -> None:
                if len(item_rows) <= 1:
                    ui.notify("At least one item is required.", color="warning")
                    return
                item_rows.remove(row_data)
                row_box.delete()
                recalc_totals()

            remove_btn.on("click", lambda _: remove_row())
            qty_input.on("change", lambda _: recalc_totals())
            purchase_price_input.on("change", lambda _: recalc_totals())
            selling_price_input.on("change", lambda _: recalc_totals())
            recalc_totals()

        paid_amount_input.on("change", lambda _: recalc_totals())

        with ui.row().classes("w-full justify-between q-mt-sm"):
            ui.button("Add Item", icon="add", on_click=lambda: add_item_row()).props("flat")
            with ui.row().classes("gap-2"):
                ui.button("Cancel", on_click=add_dialog.close, color="grey-6")

                def submit_purchase() -> None:
                    try:
                        items_payload = []
                        for row in item_rows:
                            items_payload.append(
                                {
                                    "product_id": row["product"].value,
                                    "quantity": row["quantity"].value,
                                    "purchase_price": row["purchase_price"].value,
                                    "selling_price": row["selling_price"].value,
                                }
                            )
                        purchase_number = create_purchase_record(
                            {
                                "supplier_id": add_supplier_select.value,
                                "purchase_date": add_purchase_date_input.value,
                                "notes": add_notes_input.value,
                                "paid_amount": paid_amount_input.value,
                                "items": items_payload,
                            }
                        )
                        add_dialog.close()
                        refresh_table()
                        ui.notify(f"Purchase {purchase_number} created successfully.", color="positive")
                    except ValueError as exc:
                        ui.notify(str(exc), color="warning")
                    except SQLAlchemyError:
                        ui.notify("Failed to create purchase.", color="negative")

                ui.button("Save Purchase", on_click=submit_purchase, color="primary")

        def open_add_dialog() -> None:
            nonlocal supplier_options, product_options
            supplier_options = load_supplier_options()
            product_options = load_product_options()
            add_supplier_select.options = {
                "": "Select supplier",
                **{key: value for key, value in supplier_options.items() if key},
            }
            add_supplier_select.value = ""
            add_supplier_select.update()
            add_purchase_date_input.value = datetime.now().strftime("%Y-%m-%d")
            add_notes_input.value = ""
            paid_amount_input.value = "0.00"
            total_amount_display.value = "0.00"
            remaining_amount_display.value = "0.00"
            payment_status_display.value = "Unpaid"
            for row in list(item_rows):
                row["container"].delete()
                item_rows.remove(row)
            add_item_row()
            add_dialog.open()

    def open_details(row: dict[str, Any]) -> None:
        detail = load_purchase_detail(int(row["id"]))
        if detail is None:
            ui.notify("Purchase not found.", color="warning")
            return
        details_title.text = f'Purchase Details: {detail["purchase_number"]}'
        info_line.text = (
            f'Supplier: {detail["supplier"]} | Date: {detail["purchase_date"]} | '
            f'Status: {detail["payment_status"]}'
        )
        totals_line.text = (
            f'Total: {detail["total_amount"]} | Paid: {detail["paid_amount"]} | '
            f'Remaining: {detail["remaining_amount"]}'
        )
        notes_line.text = f'Notes: {detail["notes"] or "-"}'
        details_items_table.rows = detail["items"]
        details_items_table.update()
        details_dialog.open()

    with ui.row().classes("w-full q-mb-md justify-center"):
        with ui.row().classes("w-full max-w-3xl items-end justify-center gap-2"):
            search_input = ui.input(
                label="Search Purchase / Supplier",
                placeholder="Search by purchase number or supplier",
                on_change=lambda e: filters.__setitem__("search", e.value or ""),
            ).classes("w-full max-w-2xl")
            ui.button("Search", on_click=refresh_table, icon="search")
            ui.button("Add Purchase", on_click=lambda: open_add_dialog(), icon="add", color="primary")

    with ui.card().classes("w-full q-pa-md"):
        with ui.row().classes("w-full items-start gap-4 no-wrap"):
            with ui.column().classes("w-[280px] min-w-[250px] max-w-[300px]"):
                ui.label("Filters").classes("text-subtitle1 q-mb-sm")
                supplier_filter_select = ui.select(
                    options=supplier_options,
                    label="Supplier",
                    value="",
                    with_input=True,
                    on_change=lambda e: filters.__setitem__("supplier_id", e.value or ""),
                ).classes("w-full q-mb-sm")
                payment_status_select = ui.select(
                    options=payment_status_options,
                    label="Payment Status",
                    value="",
                    with_input=True,
                    on_change=lambda e: filters.__setitem__("payment_status", e.value or ""),
                ).classes("w-full q-mb-md")

                def reset_filters() -> None:
                    filters["search"] = ""
                    filters["supplier_id"] = ""
                    filters["payment_status"] = ""
                    search_input.value = ""
                    supplier_filter_select.value = ""
                    payment_status_select.value = ""
                    search_input.update()
                    supplier_filter_select.update()
                    payment_status_select.update()
                    refresh_table()

                ui.button("Apply Filters", on_click=refresh_table, icon="filter_alt").classes("w-full")
                ui.button("Reset Filters", on_click=reset_filters, icon="refresh").classes("w-full q-mt-sm")

            with ui.column().classes("flex-1 min-w-0"):
                with ui.element("div").classes("w-full overflow-auto").style("max-height: calc(100vh - 300px);"):
                    purchases_table = ui.table(
                        columns=purchase_columns,
                        rows=[],
                        row_key="id",
                        pagination=15,
                    ).classes("w-full")

    purchases_table.add_slot(
        "body-cell-actions",
        """
        <q-td :props="props">
          <q-btn dense flat round icon="visibility" color="primary"
            @click="$parent.$emit('view_purchase', props.row)" />
        </q-td>
        """,
    )
    purchases_table.on("view_purchase", lambda e: open_details(e.args))

    refresh_table()