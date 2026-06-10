from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from nicegui import ui
from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from database import SessionLocal
from models import Customer, Debtor, Inventory, Product, Sale, SaleItem, StockMovement
from pages.layout import with_master_layout


NEW_CUSTOMER_OPTION = "__new_customer__"


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
        raise ValueError("Sale Date must be a valid date.") from exc


def load_customer_options() -> dict[str, str]:
    with SessionLocal() as session:
        customers = session.scalars(
            select(Customer).order_by(func.lower(Customer.full_name).asc())
        ).all()
    return {
        "": "Select customer",
        **{str(item.id): f"{item.full_name} ({item.phone or '-'})" for item in customers},
        NEW_CUSTOMER_OPTION: "➕ New Customer",
    }


def load_customer_map() -> dict[str, dict[str, str]]:
    with SessionLocal() as session:
        customers = session.scalars(select(Customer)).all()
    return {
        str(item.id): {
            "full_name": item.full_name,
            "phone": item.phone or "",
            "address": item.address or "",
            "notes": item.notes or "",
        }
        for item in customers
    }


def load_product_options() -> dict[str, str]:
    with SessionLocal() as session:
        products = session.scalars(
            select(Product).order_by(func.lower(Product.name).asc())
        ).all()
    return {str(item.id): item.name for item in products}


def create_customer_record(data: dict[str, Any]) -> Customer:
    full_name = str(data.get("full_name", "")).strip()
    if not full_name:
        raise ValueError("Customer name is required.")
    with SessionLocal.begin() as session:
        customer = Customer(
            full_name=full_name,
            phone=_clean_text(data.get("phone")),
            address=_clean_text(data.get("address")),
            notes=_clean_text(data.get("notes")),
        )
        session.add(customer)
        session.flush()
        session.refresh(customer)
        return customer


def load_product_map() -> dict[str, dict[str, str]]:
    with SessionLocal() as session:
        products = session.scalars(select(Product)).all()
    return {
        str(item.id): {
            "size": item.size or "",
            "pressure": item.pressure or "",
        }
        for item in products
    }


def generate_sale_number(session: Any) -> str:
    latest_number = session.scalar(select(Sale.sale_number).order_by(Sale.id.desc()).limit(1))
    if latest_number and latest_number.startswith("SAL-"):
        suffix = latest_number.replace("SAL-", "").strip()
        if suffix.isdigit():
            return f"SAL-{int(suffix) + 1:06d}"
    max_id = session.scalar(select(func.max(Sale.id))) or 0
    return f"SAL-{int(max_id) + 1:06d}"


def load_sale_rows(filters: dict[str, str]) -> list[dict[str, Any]]:
    with SessionLocal() as session:
        stmt = (
            select(Sale)
            .options(selectinload(Sale.customer), selectinload(Sale.items))
            .order_by(Sale.sale_date.desc(), Sale.id.desc())
        )
        if filters["search"].strip():
            term = f'%{filters["search"].strip()}%'
            stmt = stmt.where(
                or_(
                    Sale.sale_number.ilike(term),
                    Sale.customer.has(
                        or_(
                            Customer.full_name.ilike(term),
                            Customer.phone.ilike(term),
                        )
                    ),
                )
            )
        if filters["customer_id"].strip():
            stmt = stmt.where(Sale.customer_id == int(filters["customer_id"]))
        if filters["payment_status"].strip():
            stmt = stmt.where(Sale.payment_status == filters["payment_status"])

        sales = session.scalars(stmt).all()

    return [
        {
            "id": sale.id,
            "sale_number": sale.sale_number,
            "sale_date": sale.sale_date.strftime("%Y-%m-%d"),
            "customer": sale.customer.full_name if sale.customer else "",
            "items_count": len(sale.items),
            "total_amount": f"{sale.total_amount:.2f}",
            "paid_amount": f"{sale.paid_amount:.2f}",
            "remaining_amount": f"{sale.remaining_amount:.2f}",
            "payment_status": sale.payment_status or "",
        }
        for sale in sales
    ]


def create_sale_record(data: dict[str, Any]) -> str:
    sale_date = _parse_date(str(data.get("sale_date", "")).strip())
    customer_id_raw = str(data.get("customer_id", "")).strip()
    sale_notes = _clean_text(data.get("notes"))
    if not customer_id_raw:
        raise ValueError("Customer is required.")
    if customer_id_raw == NEW_CUSTOMER_OPTION:
        raise ValueError("Please create and select a customer.")

    item_payloads = data.get("items", [])
    if not item_payloads:
        raise ValueError("At least one sale item is required.")

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
        unit_price = _to_decimal(item.get("unit_price", "0"))
        if unit_price < Decimal("0.00"):
            raise ValueError("Unit Price cannot be negative.")
        line_total = (unit_price * Decimal(quantity)).quantize(Decimal("0.01"))
        total_amount += line_total
        parsed_items.append(
            {
                "product_id": int(product_id_raw),
                "quantity": quantity,
                "unit_price": unit_price,
                "total_price": line_total,
            }
        )
    total_amount = total_amount.quantize(Decimal("0.01"))
    paid_amount = _to_decimal(data.get("paid_amount", "0"))
    if paid_amount < Decimal("0.00"):
        raise ValueError("Paid Amount cannot be negative.")
    remaining_amount, payment_status = _payment_summary(total_amount, paid_amount)

    with SessionLocal.begin() as session:
        customer = session.get(Customer, int(customer_id_raw))
        if customer is None:
            raise ValueError("Selected customer not found.")
        customer_id = customer.id

        sale_number = generate_sale_number(session)
        sale = Sale(
            sale_number=sale_number,
            customer_id=customer_id,
            sale_date=sale_date,
            payment_type="MANUAL",
            payment_status=payment_status,
            total_amount=total_amount,
            paid_amount=paid_amount,
            remaining_amount=remaining_amount,
            notes=sale_notes,
        )
        session.add(sale)
        session.flush()

        for item in parsed_items:
            product = session.get(Product, int(item["product_id"]))
            if product is None:
                raise ValueError("Selected product not found.")

            inventory = session.get(Inventory, product.id)
            current_qty = inventory.quantity if inventory is not None else 0
            if current_qty - int(item["quantity"]) < 0:
                raise ValueError(f"Insufficient stock for product: {product.name}")

            sale_item = SaleItem(
                sale_id=sale.id,
                product_id=product.id,
                quantity=int(item["quantity"]),
                unit_price=item["unit_price"],
                total_price=item["total_price"],
            )
            session.add(sale_item)

            if inventory is None:
                inventory = Inventory(product_id=product.id, quantity=0)
                session.add(inventory)
                session.flush()
            inventory.quantity -= int(item["quantity"])

            movement = StockMovement(
                product_id=product.id,
                movement_type="OUT",
                quantity=int(item["quantity"]),
                reference_type="SALE",
                reference_id=sale.id,
                notes=f"Sale {sale.sale_number}",
            )
            session.add(movement)

        if paid_amount < total_amount and customer_id is not None:
            debtor = Debtor(
                sale_id=sale.id,
                customer_id=customer_id,
                total_debt=total_amount,
                paid_amount=paid_amount,
                remaining_amount=remaining_amount,
                due_date=None,
                status="Open",
            )
            session.add(debtor)

        return sale_number


def load_sale_detail(sale_id: int) -> dict[str, Any] | None:
    with SessionLocal() as session:
        sale = session.scalar(
            select(Sale)
            .where(Sale.id == sale_id)
            .options(selectinload(Sale.customer), selectinload(Sale.items).selectinload(SaleItem.product))
        )
        if sale is None:
            return None
        return {
            "sale_number": sale.sale_number,
            "sale_date": sale.sale_date.strftime("%Y-%m-%d"),
            "customer": sale.customer.full_name if sale.customer else "",
            "total_amount": f"{sale.total_amount:.2f}",
            "paid_amount": f"{sale.paid_amount:.2f}",
            "remaining_amount": f"{sale.remaining_amount:.2f}",
            "payment_status": sale.payment_status or "",
            "notes": sale.notes or "",
            "items": [
                {
                    "product_name": item.product.name if item.product else "",
                    "quantity": item.quantity,
                    "unit_price": f"{item.unit_price:.2f}",
                    "total_price": f"{item.total_price:.2f}",
                }
                for item in sale.items
            ],
        }


@ui.page("/sales")
@with_master_layout("Sales")
def sales_page() -> None:
    filters = {"search": "", "customer_id": "", "payment_status": ""}
    payment_status_options = {"": "All", "Paid": "Paid", "Partially Paid": "Partially Paid", "Unpaid": "Unpaid"}
    customer_options = load_customer_options()
    customer_map = load_customer_map()
    product_options = load_product_options()
    product_map = load_product_map()

    ui.label("Sales").classes("text-h4 q-mb-md")

    sale_columns = [
        {"name": "sale_number", "label": "Sale Number", "field": "sale_number", "align": "left"},
        {"name": "sale_date", "label": "Sale Date", "field": "sale_date", "align": "left"},
        {"name": "customer", "label": "Customer", "field": "customer", "align": "left"},
        {"name": "items_count", "label": "Items Count", "field": "items_count", "align": "right"},
        {"name": "total_amount", "label": "Total Amount", "field": "total_amount", "align": "right"},
        {"name": "paid_amount", "label": "Paid Amount", "field": "paid_amount", "align": "right"},
        {"name": "remaining_amount", "label": "Remaining Amount", "field": "remaining_amount", "align": "right"},
        {"name": "payment_status", "label": "Payment Status", "field": "payment_status", "align": "center"},
        {"name": "actions", "label": "Actions", "field": "actions", "align": "center"},
    ]
    sales_table: Any = None
    search_input: Any = None
    customer_filter_select: Any = None
    payment_status_select: Any = None

    def refresh_table() -> None:
        nonlocal customer_options, customer_map
        try:
            customer_options = load_customer_options()
            customer_map = load_customer_map()
            if customer_filter_select is not None:
                customer_filter_select.options = customer_options
                customer_filter_select.update()
            if sales_table is None:
                return
            sales_table.rows = load_sale_rows(filters)
            sales_table.update()
        except SQLAlchemyError:
            ui.notify("Failed to load sales.", color="negative")

    with ui.dialog() as details_dialog, ui.card().classes("w-[900px] max-w-full"):
        details_title = ui.label("Sale Details").classes("text-h6")
        info_line = ui.label("")
        totals_line = ui.label("")
        notes_line = ui.label("")
        detail_columns = [
            {"name": "product_name", "label": "Product", "field": "product_name", "align": "left"},
            {"name": "quantity", "label": "Quantity", "field": "quantity", "align": "right"},
            {"name": "unit_price", "label": "Unit Price", "field": "unit_price", "align": "right"},
            {"name": "total_price", "label": "Total", "field": "total_price", "align": "right"},
        ]
        details_items_table = ui.table(columns=detail_columns, rows=[], row_key="product_name", pagination=10).classes("w-full")
        with ui.row().classes("justify-end w-full q-mt-sm"):
            ui.button("Close", on_click=details_dialog.close, color="grey-6")

    with ui.dialog() as add_dialog, ui.card().classes("w-[1100px] max-w-full"):
        ui.label("Add Sale").classes("text-h6")

        with ui.row().classes("w-full gap-2"):
            add_customer_select = ui.select(
                options=customer_options,
                label="Customer",
                value="",
                with_input=True,
                on_change=lambda e: on_customer_change(getattr(e, "value", None)),
            ).classes("col")
            add_sale_date_input = ui.input("Sale Date", value=datetime.now().strftime("%Y-%m-%d")).props("type=date").classes("col")
        sale_notes_input = ui.textarea("Sale Notes").classes("w-full")

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
                    unit_price = _to_decimal(row["unit_price"].value or "0")
                except ValueError:
                    unit_price = Decimal("0.00")
                line_total = (unit_price * Decimal(max(qty, 0))).quantize(Decimal("0.01"))
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
                    ).classes("w-[280px]")
                    qty_input = ui.number("Quantity", value=defaults.get("quantity", 1), min=1, precision=0).classes("w-[120px]")
                    size_input = ui.input("Size", value=str(defaults.get("size", ""))).props("readonly").classes("w-[120px]")
                    pressure_input = ui.input("Pressure", value=str(defaults.get("pressure", ""))).props("readonly").classes("w-[120px]")
                    unit_price_input = ui.input("Unit Price", value=str(defaults.get("unit_price", "0.00"))).classes("w-[170px]")
                    total_input = ui.input("Total", value="0.00").props("readonly").classes("w-[150px]")
                    remove_btn = ui.button("Remove Item", color="negative")
            row_data = {
                "container": row_box,
                "product": product_select,
                "quantity": qty_input,
                "size": size_input,
                "pressure": pressure_input,
                "unit_price": unit_price_input,
                "total": total_input,
            }
            item_rows.append(row_data)

            def fill_product_meta() -> None:
                selected_raw = product_select.value
                selected_value = str(selected_raw or "").strip()
                selected_product_id = selected_value

                # When with_input is enabled, the select can sometimes hold label text.
                if selected_product_id not in product_map and selected_value:
                    for pid, label in product_options.items():
                        if label == selected_value:
                            selected_product_id = pid
                            break

                meta = product_map.get(selected_product_id, {"size": "", "pressure": ""})
                size_input.value = meta["size"]
                pressure_input.value = meta["pressure"]
                size_input.update()
                pressure_input.update()

            def remove_row() -> None:
                if len(item_rows) <= 1:
                    ui.notify("At least one item is required.", color="warning")
                    return
                item_rows.remove(row_data)
                row_box.delete()
                recalc_totals()

            remove_btn.on("click", lambda _: remove_row())
            product_select.on("change", lambda _: fill_product_meta())
            product_select.on("update:model-value", lambda _: fill_product_meta())
            qty_input.on("change", lambda _: recalc_totals())
            unit_price_input.on("change", lambda _: recalc_totals())
            fill_product_meta()
            recalc_totals()

        paid_amount_input.on("change", lambda _: recalc_totals())

        with ui.dialog() as new_customer_dialog, ui.card().classes("w-[520px] max-w-full"):
            ui.label("Create New Customer").classes("text-h6")
            new_customer_name = ui.input("Customer Name *").classes("w-full")
            new_customer_phone = ui.input("Phone").classes("w-full")
            new_customer_address = ui.input("Address").classes("w-full")
            new_customer_notes = ui.textarea("Notes").classes("w-full")
            with ui.row().classes("justify-end w-full q-mt-sm"):
                ui.button("Cancel", on_click=new_customer_dialog.close, color="grey-6")

                def submit_new_customer() -> None:
                    nonlocal customer_options, customer_map
                    try:
                        created = create_customer_record(
                            {
                                "full_name": new_customer_name.value,
                                "phone": new_customer_phone.value,
                                "address": new_customer_address.value,
                                "notes": new_customer_notes.value,
                            }
                        )
                        customer_options = load_customer_options()
                        customer_map = load_customer_map()
                        add_customer_select.options = customer_options
                        add_customer_select.value = str(created.id)
                        add_customer_select.update()
                        ui.notify("Customer created successfully.", color="positive")
                        new_customer_dialog.close()
                    except ValueError as exc:
                        ui.notify(str(exc), color="warning")
                    except SQLAlchemyError:
                        ui.notify("Failed to create customer.", color="negative")

                ui.button("Create", on_click=submit_new_customer, color="primary")

        def _normalize_customer_selection(raw: Any) -> str:
            if raw is None:
                return ""
            if isinstance(raw, dict):
                if raw.get("value") is not None:
                    return str(raw.get("value"))
                if raw.get("label") is not None:
                    return str(raw.get("label"))
            if hasattr(raw, "value"):
                return str(getattr(raw, "value") or "")
            return str(raw or "")

        def on_customer_change(raw: Any) -> None:
            selected = _normalize_customer_selection(raw)
            if selected in {NEW_CUSTOMER_OPTION, "➕ New Customer"}:
                add_customer_select.value = ""
                add_customer_select.update()
                new_customer_name.value = ""
                new_customer_phone.value = ""
                new_customer_address.value = ""
                new_customer_notes.value = ""
                new_customer_dialog.open()
                return

        add_customer_select.on(
            "update:model-value",
            lambda e: on_customer_change(
                getattr(e, "args", None)
                if getattr(e, "args", None) is not None
                else getattr(e, "value", None)
            ),
        )

        with ui.row().classes("w-full justify-between q-mt-sm"):
            ui.button("Add Item", icon="add", on_click=lambda: add_item_row()).props("flat")
            with ui.row().classes("gap-2"):
                ui.button("Cancel", on_click=add_dialog.close, color="grey-6")

                def submit_sale() -> None:
                    try:
                        items_payload = []
                        for row in item_rows:
                            items_payload.append(
                                {
                                    "product_id": row["product"].value,
                                    "quantity": row["quantity"].value,
                                    "unit_price": row["unit_price"].value,
                                }
                            )
                        sale_number = create_sale_record(
                            {
                                "customer_id": add_customer_select.value,
                                "sale_date": add_sale_date_input.value,
                                "notes": sale_notes_input.value,
                                "paid_amount": paid_amount_input.value,
                                "items": items_payload,
                            }
                        )
                        add_dialog.close()
                        refresh_table()
                        ui.notify(f"Sale {sale_number} created successfully.", color="positive")
                    except ValueError as exc:
                        ui.notify(str(exc), color="warning")
                    except SQLAlchemyError:
                        ui.notify("Failed to create sale.", color="negative")

                ui.button("Save Sale", on_click=submit_sale, color="primary")

        def open_add_dialog() -> None:
            nonlocal customer_options, customer_map, product_options, product_map
            customer_options = load_customer_options()
            customer_map = load_customer_map()
            product_options = load_product_options()
            product_map = load_product_map()
            add_customer_select.options = customer_options
            add_customer_select.value = ""
            add_customer_select.update()
            add_sale_date_input.value = datetime.now().strftime("%Y-%m-%d")
            sale_notes_input.value = ""
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
        detail = load_sale_detail(int(row["id"]))
        if detail is None:
            ui.notify("Sale not found.", color="warning")
            return
        details_title.text = f'Sale Details: {detail["sale_number"]}'
        info_line.text = (
            f'Customer: {detail["customer"]} | Date: {detail["sale_date"]} | '
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
                label="Search Sale / Customer",
                placeholder="Search by sale number or customer",
                on_change=lambda e: filters.__setitem__("search", e.value or ""),
            ).classes("w-full max-w-2xl")
            ui.button("Search", on_click=refresh_table, icon="search")
            ui.button("Add Sale", on_click=lambda: open_add_dialog(), icon="add", color="primary")

    with ui.card().classes("w-full q-pa-md"):
        with ui.row().classes("w-full items-start gap-4 no-wrap"):
            with ui.column().classes("w-[280px] min-w-[250px] max-w-[300px]"):
                ui.label("Filters").classes("text-subtitle1 q-mb-sm")
                customer_filter_select = ui.select(
                    options=customer_options,
                    label="Customer",
                    value="",
                    with_input=True,
                    on_change=lambda e: filters.__setitem__("customer_id", e.value or ""),
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
                    filters["customer_id"] = ""
                    filters["payment_status"] = ""
                    search_input.value = ""
                    customer_filter_select.value = ""
                    payment_status_select.value = ""
                    search_input.update()
                    customer_filter_select.update()
                    payment_status_select.update()
                    refresh_table()

                ui.button("Apply Filters", on_click=refresh_table, icon="filter_alt").classes("w-full")
                ui.button("Reset Filters", on_click=reset_filters, icon="refresh").classes("w-full q-mt-sm")

            with ui.column().classes("flex-1 min-w-0"):
                with ui.element("div").classes("w-full overflow-auto").style("max-height: calc(100vh - 300px);"):
                    sales_table = ui.table(
                        columns=sale_columns,
                        rows=[],
                        row_key="id",
                        pagination=15,
                    ).classes("w-full")

    sales_table.add_slot(
        "body-cell-actions",
        """
        <q-td :props="props">
          <q-btn dense flat round icon="visibility" color="primary"
            @click="$parent.$emit('view_sale', props.row)" />
        </q-td>
        """,
    )
    sales_table.on("view_sale", lambda e: open_details(e.args))

    refresh_table()