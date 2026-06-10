from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from nicegui import ui
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from database import SessionLocal
from models import Customer, Debtor, DebtorPayment, Sale
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


def _status_from_remaining(remaining_amount: Decimal) -> str:
    if remaining_amount <= Decimal("0.00"):
        return "Paid"
    return "Active"


def load_customer_options() -> dict[str, str]:
    with SessionLocal() as session:
        customers = session.scalars(
            select(Customer).order_by(func.lower(Customer.full_name).asc())
        ).all()
    return {"": "All", **{str(item.id): item.full_name for item in customers}}


def load_debtor_rows(filters: dict[str, str]) -> list[dict[str, Any]]:
    with SessionLocal() as session:
        stmt = (
            select(Debtor)
            .options(selectinload(Debtor.customer), selectinload(Debtor.sale))
            .order_by(Debtor.created_at.desc(), Debtor.id.desc())
        )
        if filters["search"].strip():
            term = f'%{filters["search"].strip()}%'
            stmt = stmt.where(
                or_(
                    Debtor.customer.has(
                        or_(
                            Customer.full_name.ilike(term),
                            Customer.phone.ilike(term),
                        )
                    ),
                    Debtor.sale.has(Sale.sale_number.ilike(term)),
                )
            )
        if filters["customer_id"].strip():
            stmt = stmt.where(Debtor.customer_id == int(filters["customer_id"]))
        if filters["status"].strip():
            if filters["status"] == "Paid":
                stmt = stmt.where(Debtor.remaining_amount <= Decimal("0.00"))
            else:
                stmt = stmt.where(Debtor.remaining_amount > Decimal("0.00"))
        if filters["due_filter"].strip() == "overdue":
            stmt = stmt.where(
                and_(
                    Debtor.due_date.is_not(None),
                    Debtor.due_date < date.today(),
                    Debtor.remaining_amount > Decimal("0.00"),
                )
            )
        if filters["due_filter"].strip() == "due_today":
            stmt = stmt.where(
                and_(
                    Debtor.due_date == date.today(),
                    Debtor.remaining_amount > Decimal("0.00"),
                )
            )

        debtors = session.scalars(stmt).all()

    return [
        {
            "id": debtor.id,
            "customer": debtor.customer.full_name if debtor.customer else "",
            "sale_number": debtor.sale.sale_number if debtor.sale else "",
            "total_debt": f"{debtor.total_debt:.2f}",
            "paid_amount": f"{debtor.paid_amount:.2f}",
            "remaining_amount": f"{debtor.remaining_amount:.2f}",
            "due_date": debtor.due_date.isoformat() if debtor.due_date else "-",
            "status": _status_from_remaining(debtor.remaining_amount),
        }
        for debtor in debtors
    ]


def load_dashboard_stats() -> dict[str, str]:
    with SessionLocal() as session:
        active_debtors = session.scalar(
            select(func.count(Debtor.id)).where(Debtor.remaining_amount > Decimal("0.00"))
        ) or 0
        total_outstanding = session.scalar(
            select(func.coalesce(func.sum(Debtor.remaining_amount), 0)).where(
                Debtor.remaining_amount > Decimal("0.00")
            )
        ) or Decimal("0.00")
        overdue_debts = session.scalar(
            select(func.count(Debtor.id)).where(
                and_(
                    Debtor.due_date.is_not(None),
                    Debtor.due_date < date.today(),
                    Debtor.remaining_amount > Decimal("0.00"),
                )
            )
        ) or 0

        now = datetime.now()
        month_start = datetime(now.year, now.month, 1)
        next_month_start = (
            datetime(now.year + 1, 1, 1)
            if now.month == 12
            else datetime(now.year, now.month + 1, 1)
        )
        collected_this_month = session.scalar(
            select(func.coalesce(func.sum(DebtorPayment.amount), 0)).where(
                and_(
                    DebtorPayment.payment_date >= month_start,
                    DebtorPayment.payment_date < next_month_start,
                )
            )
        ) or Decimal("0.00")

    return {
        "active_debtors": str(int(active_debtors)),
        "total_outstanding": f"{Decimal(total_outstanding):.2f}",
        "overdue_debts": str(int(overdue_debts)),
        "collected_this_month": f"{Decimal(collected_this_month):.2f}",
    }


def load_debtor_detail(debtor_id: int) -> dict[str, Any] | None:
    with SessionLocal() as session:
        debtor = session.scalar(
            select(Debtor)
            .where(Debtor.id == debtor_id)
            .options(
                selectinload(Debtor.customer),
                selectinload(Debtor.sale),
                selectinload(Debtor.payments),
            )
        )
        if debtor is None:
            return None

        payments = sorted(
            debtor.payments,
            key=lambda p: (p.payment_date, p.id),
            reverse=True,
        )
        return {
            "customer": debtor.customer.full_name if debtor.customer else "",
            "customer_phone": debtor.customer.phone if debtor.customer else "",
            "sale_number": debtor.sale.sale_number if debtor.sale else "",
            "sale_date": debtor.sale.sale_date.strftime("%Y-%m-%d")
            if debtor.sale and debtor.sale.sale_date
            else "",
            "total_debt": f"{debtor.total_debt:.2f}",
            "paid_amount": f"{debtor.paid_amount:.2f}",
            "remaining_amount": f"{debtor.remaining_amount:.2f}",
            "due_date": debtor.due_date.isoformat() if debtor.due_date else "-",
            "status": _status_from_remaining(debtor.remaining_amount),
            "payments": [
                {
                    "id": payment.id,
                    "payment_date": payment.payment_date.strftime("%Y-%m-%d %H:%M"),
                    "amount": f"{payment.amount:.2f}",
                    "payment_type": payment.payment_type or "",
                    "notes": payment.notes or "",
                }
                for payment in payments
            ],
        }


def receive_debtor_payment(data: dict[str, Any]) -> None:
    debtor_id_raw = str(data.get("debtor_id", "")).strip()
    if not debtor_id_raw:
        raise ValueError("Debtor is required.")
    amount = _to_decimal(data.get("amount", "0"))
    if amount <= Decimal("0.00"):
        raise ValueError("Payment amount must be greater than zero.")
    payment_date_raw = str(data.get("payment_date", "")).strip()
    if not payment_date_raw:
        raise ValueError("Payment date is required.")
    try:
        payment_dt = datetime.strptime(payment_date_raw, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("Payment date must be valid.") from exc

    with SessionLocal.begin() as session:
        debtor = session.get(Debtor, int(debtor_id_raw))
        if debtor is None:
            raise ValueError("Debtor not found.")
        if debtor.remaining_amount <= Decimal("0.00"):
            raise ValueError("This debt is already fully paid.")
        if amount > debtor.remaining_amount:
            raise ValueError("Payment amount cannot exceed remaining amount.")

        payment = DebtorPayment(
            debtor_id=debtor.id,
            payment_date=payment_dt,
            amount=amount,
            payment_type=_clean_text(data.get("payment_type")),
            notes=_clean_text(data.get("notes")),
        )
        session.add(payment)

        debtor.paid_amount = (debtor.paid_amount + amount).quantize(Decimal("0.01"))
        debtor.remaining_amount = (debtor.total_debt - debtor.paid_amount).quantize(
            Decimal("0.01")
        )
        if debtor.remaining_amount < Decimal("0.00"):
            debtor.remaining_amount = Decimal("0.00")
        debtor.status = _status_from_remaining(debtor.remaining_amount)


@ui.page("/debtors")
@with_master_layout("Debtors")
def debtors_page() -> None:
    filters = {"search": "", "customer_id": "", "status": "", "due_filter": ""}
    status_options = {"": "All", "Active": "Active", "Paid": "Paid"}
    due_filter_options = {"": "All", "overdue": "Overdue", "due_today": "Due Today"}
    customer_options = load_customer_options()

    ui.label("Debtors").classes("text-h4 q-mb-md")

    debtors_columns = [
        {"name": "customer", "label": "Customer", "field": "customer", "align": "left"},
        {"name": "sale_number", "label": "Sale Number", "field": "sale_number", "align": "left"},
        {"name": "total_debt", "label": "Total Debt", "field": "total_debt", "align": "right"},
        {"name": "paid_amount", "label": "Paid Amount", "field": "paid_amount", "align": "right"},
        {
            "name": "remaining_amount",
            "label": "Remaining Amount",
            "field": "remaining_amount",
            "align": "right",
        },
        {"name": "due_date", "label": "Due Date", "field": "due_date", "align": "left"},
        {"name": "status", "label": "Status", "field": "status", "align": "center"},
        {"name": "actions", "label": "Actions", "field": "actions", "align": "center"},
    ]
    debtors_table: Any = None
    search_input: Any = None
    customer_filter_select: Any = None
    status_filter_select: Any = None
    due_filter_select: Any = None

    stat_active_debtors: Any = None
    stat_total_outstanding: Any = None
    stat_overdue_debts: Any = None
    stat_collected_this_month: Any = None

    def refresh_page() -> None:
        nonlocal customer_options
        try:
            customer_options = load_customer_options()
            if customer_filter_select is not None:
                customer_filter_select.options = customer_options
                customer_filter_select.update()

            rows = load_debtor_rows(filters)
            if debtors_table is not None:
                debtors_table.rows = rows
                debtors_table.update()

            stats = load_dashboard_stats()
            stat_active_debtors.text = stats["active_debtors"]
            stat_total_outstanding.text = stats["total_outstanding"]
            stat_overdue_debts.text = stats["overdue_debts"]
            stat_collected_this_month.text = stats["collected_this_month"]
        except SQLAlchemyError:
            ui.notify("Failed to load debtors.", color="negative")

    with ui.dialog() as details_dialog, ui.card().classes("w-[1000px] max-w-full"):
        details_title = ui.label("Debtor Details").classes("text-h6")
        debtor_info_line = ui.label("")
        summary_info_line = ui.label("")
        payment_columns = [
            {"name": "payment_date", "label": "Payment Date", "field": "payment_date", "align": "left"},
            {"name": "amount", "label": "Amount", "field": "amount", "align": "right"},
            {"name": "payment_type", "label": "Payment Type", "field": "payment_type", "align": "left"},
            {"name": "notes", "label": "Notes", "field": "notes", "align": "left"},
        ]
        payment_history_table = ui.table(
            columns=payment_columns,
            rows=[],
            row_key="id",
            pagination=10,
        ).classes("w-full")
        with ui.row().classes("justify-end w-full q-mt-sm"):
            ui.button("Close", on_click=details_dialog.close, color="grey-6")

    selected_debtor: dict[str, Any] | None = None
    with ui.dialog() as payment_dialog, ui.card().classes("w-[500px] max-w-full"):
        ui.label("Receive Payment").classes("text-h6")
        payment_info_line = ui.label("")
        payment_remaining_line = ui.label("")
        receive_date_input = ui.input(
            "Payment Date",
            value=datetime.now().strftime("%Y-%m-%d"),
        ).props("type=date").classes("w-full")
        receive_amount_input = ui.input("Amount").classes("w-full")
        receive_type_input = ui.input("Payment Type").classes("w-full")
        receive_notes_input = ui.textarea("Notes").classes("w-full")
        with ui.row().classes("justify-end w-full q-mt-sm"):
            ui.button("Cancel", on_click=payment_dialog.close, color="grey-6")

            def submit_receive_payment() -> None:
                nonlocal selected_debtor
                if selected_debtor is None:
                    return
                try:
                    receive_debtor_payment(
                        {
                            "debtor_id": selected_debtor["id"],
                            "payment_date": receive_date_input.value,
                            "amount": receive_amount_input.value,
                            "payment_type": receive_type_input.value,
                            "notes": receive_notes_input.value,
                        }
                    )
                    ui.notify("Payment recorded successfully.", color="positive")
                    payment_dialog.close()
                    refresh_page()
                except ValueError as exc:
                    ui.notify(str(exc), color="warning")
                except SQLAlchemyError:
                    ui.notify("Failed to record payment.", color="negative")

            ui.button("Save Payment", on_click=submit_receive_payment, color="primary")

    def open_details(row: dict[str, Any]) -> None:
        detail = load_debtor_detail(int(row["id"]))
        if detail is None:
            ui.notify("Debtor not found.", color="warning")
            return

        details_title.text = f'Debtor Details: {detail["sale_number"]}'
        debtor_info_line.text = (
            f'Customer: {detail["customer"]} ({detail["customer_phone"] or "-"}) | '
            f'Sale: {detail["sale_number"]} | Sale Date: {detail["sale_date"]}'
        )
        summary_info_line.text = (
            f'Total: {detail["total_debt"]} | Paid: {detail["paid_amount"]} | '
            f'Remaining: {detail["remaining_amount"]} | Due: {detail["due_date"]} | '
            f'Status: {detail["status"]}'
        )
        payment_history_table.rows = detail["payments"]
        payment_history_table.update()
        details_dialog.open()

    def open_receive_payment(row: dict[str, Any]) -> None:
        nonlocal selected_debtor
        if str(row["status"]).strip() == "Paid":
            ui.notify("This debt is already fully paid.", color="warning")
            return
        selected_debtor = row
        payment_info_line.text = (
            f'Customer: {row["customer"]} | Sale: {row["sale_number"]}'
        )
        payment_remaining_line.text = f'Remaining Amount: {row["remaining_amount"]}'
        receive_date_input.value = datetime.now().strftime("%Y-%m-%d")
        receive_amount_input.value = ""
        receive_type_input.value = ""
        receive_notes_input.value = ""
        payment_dialog.open()

    with ui.row().classes("w-full q-mb-md justify-center"):
        with ui.row().classes("w-full max-w-3xl items-end justify-center gap-2"):
            search_input = ui.input(
                label="Search Customer / Sale Number",
                placeholder="Search by customer or sale number",
                on_change=lambda e: filters.__setitem__("search", e.value or ""),
            ).classes("w-full max-w-2xl")
            ui.button("Search", on_click=refresh_page, icon="search")

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
                status_filter_select = ui.select(
                    options=status_options,
                    label="Status",
                    value="",
                    on_change=lambda e: filters.__setitem__("status", e.value or ""),
                ).classes("w-full q-mb-sm")
                due_filter_select = ui.select(
                    options=due_filter_options,
                    label="Due Date Filter",
                    value="",
                    on_change=lambda e: filters.__setitem__("due_filter", e.value or ""),
                ).classes("w-full q-mb-md")

                def reset_filters() -> None:
                    filters["search"] = ""
                    filters["customer_id"] = ""
                    filters["status"] = ""
                    filters["due_filter"] = ""
                    search_input.value = ""
                    customer_filter_select.value = ""
                    status_filter_select.value = ""
                    due_filter_select.value = ""
                    search_input.update()
                    customer_filter_select.update()
                    status_filter_select.update()
                    due_filter_select.update()
                    refresh_page()

                ui.button("Apply Filters", on_click=refresh_page, icon="filter_alt").classes(
                    "w-full"
                )
                ui.button("Reset Filters", on_click=reset_filters, icon="refresh").classes(
                    "w-full q-mt-sm"
                )

            with ui.column().classes("flex-1 min-w-0"):
                with ui.element("div").classes("w-full overflow-auto").style(
                    "max-height: calc(100vh - 360px);"
                ):
                    debtors_table = ui.table(
                        columns=debtors_columns,
                        rows=[],
                        row_key="id",
                        pagination=15,
                    ).classes("w-full")

    with ui.row().classes("w-full items-stretch q-gutter-sm q-mt-md q-mb-md"):
        with ui.card().classes("flex-1 min-w-[180px] q-pa-md"):
            stat_active_debtors = ui.label("0").classes(
                "text-h4 text-weight-bold text-center"
            )
            ui.label("Active Debtors").classes("text-subtitle2 text-grey-8 text-center")
        with ui.card().classes("flex-1 min-w-[180px] q-pa-md"):
            stat_total_outstanding = ui.label("0.00").classes(
                "text-h4 text-weight-bold text-center"
            )
            ui.label("Total Outstanding Debt").classes(
                "text-subtitle2 text-grey-8 text-center"
            )
        with ui.card().classes("flex-1 min-w-[180px] q-pa-md"):
            stat_overdue_debts = ui.label("0").classes(
                "text-h4 text-weight-bold text-center"
            )
            ui.label("Overdue Debts").classes("text-subtitle2 text-grey-8 text-center")
        with ui.card().classes("flex-1 min-w-[180px] q-pa-md"):
            stat_collected_this_month = ui.label("0.00").classes(
                "text-h4 text-weight-bold text-center"
            )
            ui.label("Collected This Month").classes(
                "text-subtitle2 text-grey-8 text-center"
            )

    debtors_table.add_slot(
        "body-cell-actions",
        """
        <q-td :props="props">
          <q-btn dense flat round icon="visibility" color="primary"
            @click="$parent.$emit('view_debtor', props.row)" />
          <q-btn dense flat round icon="payments" color="positive"
            @click="$parent.$emit('receive_payment', props.row)" />
        </q-td>
        """,
    )
    debtors_table.on("view_debtor", lambda e: open_details(e.args))
    debtors_table.on("receive_payment", lambda e: open_receive_payment(e.args))

    refresh_page()

