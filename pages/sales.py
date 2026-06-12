from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from nicegui import ui
from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from core.i18n import payment_status_label, t
from database import SessionLocal
from models import Customer, Debtor, Inventory, Product, Sale, SaleItem, StockMovement
from pages.components import (
    add_table_empty_state,
    data_table_card,
    filter_sidebar,
    page_header,
    search_panel,
    style_status_column,
)
from pages.layout import with_master_layout


NEW_CUSTOMER_OPTION = "__new_customer__"


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"))
    try:
        return Decimal(str(value).strip()).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, AttributeError) as exc:
        raise ValueError(t("sales.error.invalid_monetary_value")) from exc


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
        raise ValueError(t("sales.error.invalid_sale_date")) from exc


def load_customer_options() -> dict[str, str]:
    with SessionLocal() as session:
        customers = session.scalars(
            select(Customer).order_by(func.lower(Customer.full_name).asc())
        ).all()
    return {
        "": t("sales.option.select_customer"),
        **{
            str(item.id): f"{item.full_name} ({item.phone or t('common.placeholder.dash')})"
            for item in customers
        },
        NEW_CUSTOMER_OPTION: t("sales.option.new_customer"),
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
        raise ValueError(t("sales.error.customer_name_required"))
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
            "payment_status": payment_status_label(sale.payment_status or ""),
        }
        for sale in sales
    ]


def create_sale_record(data: dict[str, Any]) -> str:
    sale_date = _parse_date(str(data.get("sale_date", "")).strip())
    customer_id_raw = str(data.get("customer_id", "")).strip()
    sale_notes = _clean_text(data.get("notes"))
    if not customer_id_raw:
        raise ValueError(t("sales.error.customer_required"))
    if customer_id_raw == NEW_CUSTOMER_OPTION:
        raise ValueError(t("sales.error.select_customer"))

    item_payloads = data.get("items", [])
    if not item_payloads:
        raise ValueError(t("sales.error.at_least_one_item"))

    parsed_items: list[dict[str, Any]] = []
    total_amount = Decimal("0.00")
    for item in item_payloads:
        product_id_raw = str(item.get("product_id", "")).strip()
        if not product_id_raw:
            raise ValueError(t("sales.error.item_product_required"))
        try:
            quantity = int(item.get("quantity", 0))
        except (TypeError, ValueError) as exc:
            raise ValueError(t("sales.error.quantity_integer")) from exc
        if quantity <= 0:
            raise ValueError(t("sales.error.quantity_positive"))
        unit_price = _to_decimal(item.get("unit_price", "0"))
        if unit_price < Decimal("0.00"):
            raise ValueError(t("sales.error.unit_price_negative"))
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
        raise ValueError(t("sales.error.paid_amount_negative"))
    remaining_amount, payment_status = _payment_summary(total_amount, paid_amount)

    with SessionLocal.begin() as session:
        customer = session.get(Customer, int(customer_id_raw))
        if customer is None:
            raise ValueError(t("sales.error.customer_not_found"))
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
                raise ValueError(t("sales.error.product_not_found"))

            inventory = session.get(Inventory, product.id)
            current_qty = inventory.quantity if inventory is not None else 0
            if current_qty - int(item["quantity"]) < 0:
                raise ValueError(t("sales.error.insufficient_stock", product_name=product.name))

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
@with_master_layout(t("sales.title"))
def sales_page() -> None:
    filters = {"search": "", "customer_id": "", "payment_status": ""}
    payment_status_options = {
        "": t("common.filter.all"),
        "Paid": payment_status_label("Paid"),
        "Partially Paid": payment_status_label("Partially Paid"),
        "Unpaid": payment_status_label("Unpaid"),
    }
    customer_options = load_customer_options()
    customer_map = load_customer_map()
    product_options = load_product_options()
    product_map = load_product_map()

    page_header(t("sales.title"), t("sales.description"))

    sale_columns = [
        {"name": "sale_number", "label": t("sales.table.sale_number"), "field": "sale_number", "align": "left"},
        {"name": "sale_date", "label": t("sales.field.sale_date"), "field": "sale_date", "align": "left"},
        {"name": "customer", "label": t("sales.field.customer"), "field": "customer", "align": "left"},
        {"name": "items_count", "label": t("sales.table.items_count"), "field": "items_count", "align": "right"},
        {"name": "total_amount", "label": t("purchases.field.total_amount"), "field": "total_amount", "align": "right"},
        {"name": "paid_amount", "label": t("purchases.field.paid_amount"), "field": "paid_amount", "align": "right"},
        {"name": "remaining_amount", "label": t("purchases.field.remaining_amount"), "field": "remaining_amount", "align": "right"},
        {"name": "payment_status", "label": t("sales.filter.payment_status"), "field": "payment_status", "align": "center"},
        {"name": "actions", "label": t("common.table.actions"), "field": "actions", "align": "center"},
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
            ui.notify(t("sales.notify.load_failed"), color="negative")

    with ui.dialog() as details_dialog, ui.card().classes("w-[900px] max-w-full"):
        details_title = ui.label(t("sales.dialog.details")).classes("text-h6")
        info_line = ui.label("")
        totals_line = ui.label("")
        notes_line = ui.label("")
        detail_columns = [
            {"name": "product_name", "label": t("sales.field.product"), "field": "product_name", "align": "left"},
            {"name": "quantity", "label": t("common.table.quantity"), "field": "quantity", "align": "right"},
            {"name": "unit_price", "label": t("sales.field.unit_price"), "field": "unit_price", "align": "right"},
            {"name": "total_price", "label": t("common.table.total"), "field": "total_price", "align": "right"},
        ]
        details_items_table = ui.table(columns=detail_columns, rows=[], row_key="product_name", pagination=10).classes("w-full")
        with ui.row().classes("justify-end w-full q-mt-sm"):
            ui.button(t("common.button.close"), on_click=details_dialog.close, color="grey-6")

    with ui.dialog() as add_dialog, ui.card().classes("w-[1100px] max-w-full"):
        ui.label(t("sales.dialog.add_sale")).classes("text-h6")

        with ui.row().classes("w-full gap-2"):
            add_customer_select = ui.select(
                options=customer_options,
                label=t("sales.field.customer"),
                value="",
                with_input=True,
                on_change=lambda e: on_customer_change(getattr(e, "value", None)),
            ).classes("col")
            add_sale_date_input = ui.input(t("sales.field.sale_date"), value=datetime.now().strftime("%Y-%m-%d")).props("type=date").classes("col")
        sale_notes_input = ui.textarea(t("sales.field.sale_notes")).classes("w-full")

        ui.separator()
        ui.label(t("purchases.section.items")).classes("text-subtitle1")
        items_container = ui.column().classes("w-full gap-2")
        item_rows: list[dict[str, Any]] = []

        ui.separator()
        ui.label(t("purchases.section.payment")).classes("text-subtitle1")
        with ui.row().classes("w-full gap-2"):
            total_amount_display = ui.input(t("purchases.field.total_amount"), value="0.00").props("readonly").classes("col")
            paid_amount_input = ui.input(t("purchases.field.paid_amount"), value="0.00").classes("col")
        with ui.row().classes("w-full gap-2"):
            remaining_amount_display = ui.input(t("purchases.field.remaining_amount"), value="0.00").props("readonly").classes("col")
            payment_status_display = ui.input(t("purchases.field.payment_status"), value=payment_status_label("Unpaid")).props("readonly").classes("col")

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
            payment_status_display.value = payment_status_label(status)
            total_amount_display.update()
            remaining_amount_display.update()
            payment_status_display.update()

        def add_item_row(defaults: dict[str, Any] | None = None) -> None:
            defaults = defaults or {}
            with items_container:
                row_box = ui.row().classes("w-full items-end gap-2")
                with row_box:
                    product_select = ui.select(
                        options={"": t("sales.option.select_product"), **product_options},
                        label=t("sales.field.product"),
                        value=str(defaults.get("product_id", "")),
                        with_input=True,
                    ).classes("w-[280px]")
                    qty_input = ui.number(t("common.table.quantity"), value=defaults.get("quantity", 1), min=1, precision=0).classes("w-[120px]")
                    size_input = ui.input(t("products.field.size"), value=str(defaults.get("size", ""))).props("readonly").classes("w-[120px]")
                    pressure_input = ui.input(t("products.field.pressure"), value=str(defaults.get("pressure", ""))).props("readonly").classes("w-[120px]")
                    unit_price_input = ui.input(t("sales.field.unit_price"), value=str(defaults.get("unit_price", "0.00"))).classes("w-[170px]")
                    total_input = ui.input(t("common.table.total"), value="0.00").props("readonly").classes("w-[150px]")
                    remove_btn = ui.button(t("common.button.remove_item"), color="negative")
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
                    ui.notify(t("sales.notify.at_least_one_item"), color="warning")
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
            ui.label(t("sales.dialog.create_customer")).classes("text-h6")
            new_customer_name = ui.input(t("sales.field.customer_name_required")).classes("w-full")
            new_customer_phone = ui.input(t("suppliers.field.phone")).classes("w-full")
            new_customer_address = ui.input(t("suppliers.field.address")).classes("w-full")
            new_customer_notes = ui.textarea(t("common.table.notes")).classes("w-full")
            with ui.row().classes("justify-end w-full q-mt-sm"):
                ui.button(t("common.button.cancel"), on_click=new_customer_dialog.close, color="grey-6")

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
                        ui.notify(t("sales.notify.customer_created"), color="positive")
                        new_customer_dialog.close()
                    except ValueError as exc:
                        ui.notify(str(exc), color="warning")
                    except SQLAlchemyError:
                        ui.notify(t("sales.notify.customer_create_failed"), color="negative")

                ui.button(t("common.button.create"), on_click=submit_new_customer, color="primary")

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
            if selected in {NEW_CUSTOMER_OPTION, t("sales.option.new_customer")}:
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
            ui.button(t("common.button.add_item"), icon="add", on_click=lambda: add_item_row()).props("flat")
            with ui.row().classes("gap-2"):
                ui.button(t("common.button.cancel"), on_click=add_dialog.close, color="grey-6")

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
                        ui.notify(t("sales.notify.created", sale_number=sale_number), color="positive")
                    except ValueError as exc:
                        ui.notify(str(exc), color="warning")
                    except SQLAlchemyError:
                        ui.notify(t("sales.notify.create_failed"), color="negative")

                ui.button(t("common.button.save_sale"), on_click=submit_sale, color="primary")

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
            payment_status_display.value = payment_status_label("Unpaid")
            for row in list(item_rows):
                row["container"].delete()
                item_rows.remove(row)
            add_item_row()
            add_dialog.open()

    def open_details(row: dict[str, Any]) -> None:
        detail = load_sale_detail(int(row["id"]))
        if detail is None:
            ui.notify(t("sales.notify.not_found"), color="warning")
            return
        details_title.text = t("sales.dialog.details_number", sale_number=detail["sale_number"])
        info_line.text = t(
            "sales.details.info",
            customer=detail["customer"],
            date=detail["sale_date"],
            status=payment_status_label(detail["payment_status"]),
        )
        totals_line.text = t(
            "sales.details.totals",
            total=detail["total_amount"],
            paid=detail["paid_amount"],
            remaining=detail["remaining_amount"],
        )
        notes_line.text = t(
            "sales.details.notes",
            notes=detail["notes"] or t("common.placeholder.dash"),
        )
        details_items_table.rows = detail["items"]
        details_items_table.update()
        details_dialog.open()

    with search_panel():
        with ui.row().classes("w-full items-end no-wrap gap-3"):
            search_input = ui.input(
                label=t("sales.search.label"),
                placeholder=t("sales.search.placeholder"),
                on_change=lambda e: filters.__setitem__("search", e.value or ""),
            ).classes("flex-1 min-w-0")
            ui.button(t("common.button.search"), on_click=refresh_table, icon="search")
            ui.button(t("sales.button.add_sale"), on_click=lambda: open_add_dialog(), icon="add", color="primary")

    with ui.row().classes("w-full items-start gap-4 no-wrap"):
        with filter_sidebar():
            customer_filter_select = ui.select(
                options=customer_options,
                label=t("sales.field.customer"),
                value="",
                with_input=True,
                on_change=lambda e: filters.__setitem__("customer_id", e.value or ""),
            ).classes("w-full")
            payment_status_select = ui.select(
                options=payment_status_options,
                label=t("sales.filter.payment_status"),
                value="",
                with_input=True,
                on_change=lambda e: filters.__setitem__("payment_status", e.value or ""),
            ).classes("w-full")

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

            ui.button(t("common.button.apply_filters"), on_click=refresh_table, icon="filter_alt").classes("w-full")
            ui.button(t("common.button.reset_filters"), on_click=reset_filters, icon="refresh").classes("w-full q-mt-sm")

        with data_table_card().classes("flex-1 min-w-0"):
            with ui.element("div").classes("w-full overflow-auto").style("max-height: calc(100vh - 300px);"):
                sales_table = ui.table(
                    columns=sale_columns,
                    rows=[],
                    row_key="id",
                    pagination=15,
                ).classes("w-full")

    style_status_column(sales_table, "payment_status")
    add_table_empty_state(sales_table, t("sales.empty.no_sales"), icon="🧾")
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
