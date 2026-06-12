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
from models import Inventory, Product, Purchase, PurchaseItem, StockMovement, Supplier
from pages.components import (
    add_table_empty_state,
    data_table_card,
    filter_sidebar,
    page_header,
    search_panel,
    style_status_column,
)
from pages.layout import with_master_layout


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"))
    try:
        return Decimal(str(value).strip()).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, AttributeError) as exc:
        raise ValueError(t("purchases.error.invalid_monetary_value")) from exc


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
        raise ValueError(t("purchases.error.invalid_purchase_date")) from exc


def load_supplier_options() -> dict[str, str]:
    with SessionLocal() as session:
        suppliers = session.scalars(
            select(Supplier).order_by(func.lower(Supplier.company_name).asc())
        ).all()
    return {"": t("common.filter.all"), **{str(item.id): item.company_name for item in suppliers}}


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
            "payment_status": payment_status_label(purchase.payment_status or ""),
        }
        for purchase in purchases
    ]


def create_purchase_record(data: dict[str, Any]) -> str:
    supplier_id_raw = str(data.get("supplier_id", "")).strip()
    if not supplier_id_raw:
        raise ValueError(t("purchases.error.supplier_required"))
    purchase_date_str = str(data.get("purchase_date", "")).strip()
    purchase_date = _parse_date(purchase_date_str)

    item_payloads = data.get("items", [])
    if not item_payloads:
        raise ValueError(t("purchases.error.at_least_one_item"))

    parsed_items: list[dict[str, Any]] = []
    total_amount = Decimal("0.00")
    for item in item_payloads:
        product_id_raw = str(item.get("product_id", "")).strip()
        if not product_id_raw:
            raise ValueError(t("purchases.error.item_product_required"))
        try:
            quantity = int(item.get("quantity", 0))
        except (TypeError, ValueError) as exc:
            raise ValueError(t("purchases.error.quantity_integer")) from exc
        if quantity <= 0:
            raise ValueError(t("purchases.error.quantity_positive"))
        purchase_price = _to_decimal(item.get("purchase_price", "0"))
        selling_price = _to_decimal(item.get("selling_price", "0"))
        if purchase_price < Decimal("0.00") or selling_price < Decimal("0.00"):
            raise ValueError(t("purchases.error.prices_negative"))

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
        raise ValueError(t("purchases.error.paid_amount_negative"))
    remaining_amount, payment_status = _payment_summary(total_amount, paid_amount)
    notes = _clean_text(data.get("notes"))

    with SessionLocal.begin() as session:
        supplier = session.get(Supplier, int(supplier_id_raw))
        if supplier is None:
            raise ValueError(t("purchases.error.supplier_not_found"))

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
                raise ValueError(t("purchases.error.product_not_found"))
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
@with_master_layout(t("purchases.title"))
def purchases_page() -> None:
    filters = {"search": "", "supplier_id": "", "payment_status": ""}
    payment_status_options = {
        "": t("common.filter.all"),
        "Paid": payment_status_label("Paid"),
        "Partially Paid": payment_status_label("Partially Paid"),
        "Unpaid": payment_status_label("Unpaid"),
    }
    supplier_options = load_supplier_options()
    product_options = load_product_options()

    page_header(t("purchases.title"), t("purchases.description"))

    purchase_columns = [
        {"name": "purchase_number", "label": t("purchases.table.purchase_number"), "field": "purchase_number", "align": "left"},
        {"name": "purchase_date", "label": t("purchases.field.purchase_date"), "field": "purchase_date", "align": "left"},
        {"name": "supplier", "label": t("purchases.field.supplier"), "field": "supplier", "align": "left"},
        {"name": "items_count", "label": t("purchases.table.items_count"), "field": "items_count", "align": "right"},
        {"name": "total_amount", "label": t("purchases.field.total_amount"), "field": "total_amount", "align": "right"},
        {"name": "paid_amount", "label": t("purchases.field.paid_amount"), "field": "paid_amount", "align": "right"},
        {"name": "remaining_amount", "label": t("purchases.field.remaining_amount"), "field": "remaining_amount", "align": "right"},
        {"name": "payment_status", "label": t("purchases.field.payment_status"), "field": "payment_status", "align": "center"},
        {"name": "actions", "label": t("common.table.actions"), "field": "actions", "align": "center"},
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
            ui.notify(t("purchases.notify.load_failed"), color="negative")

    with ui.dialog() as details_dialog, ui.card().classes("w-[950px] max-w-full"):
        details_title = ui.label(t("purchases.dialog.details")).classes("text-h6")
        info_line = ui.label("")
        totals_line = ui.label("")
        notes_line = ui.label("")
        detail_item_columns = [
            {"name": "product_name", "label": t("sales.field.product"), "field": "product_name", "align": "left"},
            {"name": "quantity", "label": t("common.table.quantity"), "field": "quantity", "align": "right"},
            {"name": "purchase_price", "label": t("purchases.field.purchase_price"), "field": "purchase_price", "align": "right"},
            {"name": "selling_price", "label": t("purchases.field.selling_price"), "field": "selling_price", "align": "right"},
            {"name": "total_price", "label": t("common.table.total"), "field": "total_price", "align": "right"},
        ]
        details_items_table = ui.table(
            columns=detail_item_columns,
            rows=[],
            row_key="product_name",
            pagination=10,
        ).classes("w-full")
        with ui.row().classes("justify-end w-full q-mt-sm"):
            ui.button(t("common.button.close"), on_click=details_dialog.close, color="grey-6")

    with ui.dialog() as add_dialog, ui.card().classes("w-[1100px] max-w-full"):
        ui.label(t("purchases.dialog.add_purchase")).classes("text-h6")
        with ui.row().classes("w-full gap-2"):
            add_supplier_select = ui.select(
                options={"": t("purchases.option.select_supplier"), **{key: value for key, value in supplier_options.items() if key}},
                label=t("purchases.field.supplier"),
                value="",
                with_input=True,
            ).classes("col")
            add_purchase_date_input = ui.input(t("purchases.field.purchase_date"), value=datetime.now().strftime("%Y-%m-%d")).props("type=date").classes("col")
        add_notes_input = ui.textarea(t("common.table.notes")).classes("w-full")

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
                        options={"": t("purchases.option.select_product"), **product_options},
                        label=t("sales.field.product"),
                        value=str(defaults.get("product_id", "")),
                        with_input=True,
                    ).classes("w-[260px]")
                    qty_input = ui.number(t("common.table.quantity"), value=defaults.get("quantity", 1), min=1, precision=0).classes("w-[120px]")
                    purchase_price_input = ui.input(t("purchases.field.purchase_price"), value=str(defaults.get("purchase_price", "0.00"))).classes("w-[160px]")
                    selling_price_input = ui.input(t("purchases.field.selling_price"), value=str(defaults.get("selling_price", "0.00"))).classes("w-[160px]")
                    total_input = ui.input(t("common.table.total"), value="0.00").props("readonly").classes("w-[140px]")
                    remove_btn = ui.button(t("common.button.remove_item"), color="negative")
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
                    ui.notify(t("purchases.notify.at_least_one_item"), color="warning")
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
            ui.button(t("common.button.add_item"), icon="add", on_click=lambda: add_item_row()).props("flat")
            with ui.row().classes("gap-2"):
                ui.button(t("common.button.cancel"), on_click=add_dialog.close, color="grey-6")

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
                        ui.notify(t("purchases.notify.created", purchase_number=purchase_number), color="positive")
                    except ValueError as exc:
                        ui.notify(str(exc), color="warning")
                    except SQLAlchemyError:
                        ui.notify(t("purchases.notify.create_failed"), color="negative")

                ui.button(t("common.button.save_purchase"), on_click=submit_purchase, color="primary")

        def open_add_dialog() -> None:
            nonlocal supplier_options, product_options
            supplier_options = load_supplier_options()
            product_options = load_product_options()
            add_supplier_select.options = {
                "": t("purchases.option.select_supplier"),
                **{key: value for key, value in supplier_options.items() if key},
            }
            add_supplier_select.value = ""
            add_supplier_select.update()
            add_purchase_date_input.value = datetime.now().strftime("%Y-%m-%d")
            add_notes_input.value = ""
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
        detail = load_purchase_detail(int(row["id"]))
        if detail is None:
            ui.notify(t("purchases.notify.not_found"), color="warning")
            return
        details_title.text = t("purchases.dialog.details_number", number=detail["purchase_number"])
        info_line.text = t(
            "purchases.details.info",
            supplier=detail["supplier"],
            date=detail["purchase_date"],
            status=payment_status_label(detail["payment_status"]),
        )
        totals_line.text = t(
            "purchases.details.totals",
            total=detail["total_amount"],
            paid=detail["paid_amount"],
            remaining=detail["remaining_amount"],
        )
        notes_line.text = t(
            "purchases.details.notes",
            notes=detail["notes"] or t("common.placeholder.dash"),
        )
        details_items_table.rows = detail["items"]
        details_items_table.update()
        details_dialog.open()

    with search_panel():
        with ui.row().classes("w-full items-end no-wrap gap-3"):
            search_input = ui.input(
                label=t("purchases.search.label"),
                placeholder=t("purchases.search.placeholder"),
                on_change=lambda e: filters.__setitem__("search", e.value or ""),
            ).classes("flex-1 min-w-0")
            ui.button(t("common.button.search"), on_click=refresh_table, icon="search")
            ui.button(t("purchases.button.add_purchase"), on_click=lambda: open_add_dialog(), icon="add", color="primary")

    with ui.row().classes("w-full items-start gap-4 no-wrap"):
        with filter_sidebar():
            supplier_filter_select = ui.select(
                options=supplier_options,
                label=t("purchases.field.supplier"),
                value="",
                with_input=True,
                on_change=lambda e: filters.__setitem__("supplier_id", e.value or ""),
            ).classes("w-full")
            payment_status_select = ui.select(
                options=payment_status_options,
                label=t("purchases.filter.payment_status"),
                value="",
                with_input=True,
                on_change=lambda e: filters.__setitem__("payment_status", e.value or ""),
            ).classes("w-full")

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

            ui.button(t("common.button.apply_filters"), on_click=refresh_table, icon="filter_alt").classes("w-full")
            ui.button(t("common.button.reset_filters"), on_click=reset_filters, icon="refresh").classes("w-full q-mt-sm")

        with data_table_card().classes("flex-1 min-w-0"):
            with ui.element("div").classes("w-full overflow-auto").style("max-height: calc(100vh - 300px);"):
                purchases_table = ui.table(
                    columns=purchase_columns,
                    rows=[],
                    row_key="id",
                    pagination=15,
                ).classes("w-full")

    style_status_column(purchases_table, "payment_status")
    add_table_empty_state(purchases_table, t("purchases.empty.no_purchases"), icon="📦")
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
