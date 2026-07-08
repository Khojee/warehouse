"""PDF export for report previews (reportlab)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from core.i18n import t
from pages.settings import load_settings_values
from services.image_service import PROJECT_ROOT, get_logo_path

EXPORTS_DIR = PROJECT_ROOT / "exports"
FLOWCORE_CONTACT_PHONE = "+998913657273"

# FlowCore theme tokens (pages/layout.py)
FC_PRIMARY = colors.HexColor("#007979")
FC_PRIMARY_HOVER = colors.HexColor("#24B1B1")
FC_BG = colors.HexColor("#FFF0E4")
FC_SURFACE = colors.HexColor("#FFFFFF")
FC_SURFACE_2 = colors.HexColor("#FFE0C5")
FC_TEXT = colors.HexColor("#0F172A")
FC_MUTED = colors.HexColor("#64748B")
FC_BORDER = colors.HexColor("#E2E8F0")

_CURRENCY_FIELDS: frozenset[str] = frozenset(
    {
        "total_amount",
        "paid_amount",
        "remaining_amount",
        "total",
        "paid",
        "remaining",
        "unit_price",
        "inventory_value",
        "debt",
        "revenue",
        "total_spent",
        "total_revenue",
        "outstanding_debt",
        "warehouse_value",
        "current_price",
    }
)

_NUMERIC_FIELDS: frozenset[str] = frozenset(
    {
        "quantity",
        "quantity_sold",
        "items_count",
        "sales_count",
        "purchases_count",
        "reference_id",
        "product_id",
    }
)

_FONTS_REGISTERED = False
_FONT_REGULAR = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"


def _register_fonts() -> None:
    global _FONTS_REGISTERED, _FONT_REGULAR, _FONT_BOLD
    if _FONTS_REGISTERED:
        return
    candidates = [
        (Path(r"C:\Windows\Fonts\arial.ttf"), Path(r"C:\Windows\Fonts\arialbd.ttf")),
        (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")),
        (Path("/usr/share/fonts/TTF/DejaVuSans.ttf"), Path("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf")),
    ]
    for regular_path, bold_path in candidates:
        if regular_path.exists() and bold_path.exists():
            pdfmetrics.registerFont(TTFont("FCSans", str(regular_path)))
            pdfmetrics.registerFont(TTFont("FCSans-Bold", str(bold_path)))
            _FONT_REGULAR = "FCSans"
            _FONT_BOLD = "FCSans-Bold"
            break
    _FONTS_REGISTERED = True


def _to_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    try:
        return float(Decimal(str(value).strip().replace(",", "")))
    except (InvalidOperation, ValueError, AttributeError):
        return None


def _format_cell(value: Any, field: str) -> str:
    if value is None:
        return ""
    if field in _CURRENCY_FIELDS:
        numeric = _to_number(value)
        if numeric is not None:
            return f"{numeric:,.2f}"
    if field in _NUMERIC_FIELDS or isinstance(value, (int, float)):
        numeric = _to_number(value)
        if numeric is not None:
            if float(numeric).is_integer():
                return f"{int(numeric):,}"
            return f"{numeric:,.2f}"
    return str(value)


def _export_columns(columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        column
        for column in columns
        if column.get("field")
        and column.get("field") not in {"status_code", "movement_type_code"}
    ]


def _resolve_logo_file() -> Path | None:
    relative = get_logo_path()
    if relative:
        path = PROJECT_ROOT / relative.replace("\\", "/")
        if path.exists():
            return path
    settings = load_settings_values()
    logo_path = (settings.get("logo_path") or "").strip().replace("\\", "/")
    if logo_path:
        path = PROJECT_ROOT / logo_path
        if path.exists():
            return path
    return None


def _build_styles() -> dict[str, ParagraphStyle]:
    _register_fonts()
    base = getSampleStyleSheet()
    return {
        "company": ParagraphStyle(
            "FCCompany",
            parent=base["Normal"],
            fontName=_FONT_BOLD,
            fontSize=14,
            textColor=FC_PRIMARY,
            leading=18,
            alignment=TA_LEFT,
        ),
        "meta": ParagraphStyle(
            "FCMeta",
            parent=base["Normal"],
            fontName=_FONT_REGULAR,
            fontSize=9,
            textColor=FC_MUTED,
            leading=12,
            alignment=TA_LEFT,
        ),
        "title": ParagraphStyle(
            "FCTitle",
            parent=base["Normal"],
            fontName=_FONT_BOLD,
            fontSize=13,
            textColor=FC_TEXT,
            leading=16,
            alignment=TA_LEFT,
            spaceBefore=4,
            spaceAfter=2,
        ),
        "header_cell": ParagraphStyle(
            "FCHeaderCell",
            parent=base["Normal"],
            fontName=_FONT_BOLD,
            fontSize=8,
            textColor=colors.white,
            leading=10,
            alignment=TA_CENTER,
        ),
        "body_left": ParagraphStyle(
            "FCBodyLeft",
            parent=base["Normal"],
            fontName=_FONT_REGULAR,
            fontSize=8,
            textColor=FC_TEXT,
            leading=10,
            alignment=TA_LEFT,
        ),
        "body_right": ParagraphStyle(
            "FCBodyRight",
            parent=base["Normal"],
            fontName=_FONT_REGULAR,
            fontSize=8,
            textColor=FC_TEXT,
            leading=10,
            alignment=TA_RIGHT,
        ),
        "body_center": ParagraphStyle(
            "FCBodyCenter",
            parent=base["Normal"],
            fontName=_FONT_REGULAR,
            fontSize=8,
            textColor=FC_TEXT,
            leading=10,
            alignment=TA_CENTER,
        ),
        "footer": ParagraphStyle(
            "FCFooter",
            parent=base["Normal"],
            fontName=_FONT_REGULAR,
            fontSize=8,
            textColor=FC_MUTED,
            alignment=TA_CENTER,
        ),
    }


def _column_align(column: dict[str, Any], field: str) -> str:
    align = str(column.get("align") or "").lower()
    if align in {"left", "right", "center"}:
        return align
    if field in _CURRENCY_FIELDS or field in _NUMERIC_FIELDS:
        return "right"
    if field in {"status", "movement_type", "payment_type"}:
        return "center"
    return "left"


def _body_style_for(styles: dict[str, ParagraphStyle], align: str) -> ParagraphStyle:
    if align == "right":
        return styles["body_right"]
    if align == "center":
        return styles["body_center"]
    return styles["body_left"]


def _add_page_decorations(canvas: Any, doc: Any) -> None:
    _register_fonts()
    canvas.saveState()
    width, height = doc.pagesize

    # Top accent bar
    canvas.setFillColor(FC_PRIMARY)
    canvas.rect(0, height - 4 * mm, width, 4 * mm, fill=1, stroke=0)

    # Footer line
    canvas.setStrokeColor(FC_BORDER)
    canvas.setLineWidth(0.5)
    canvas.line(doc.leftMargin, 14 * mm, width - doc.rightMargin, 14 * mm)

    canvas.setFillColor(FC_MUTED)
    canvas.setFont(_FONT_REGULAR, 8)
    canvas.drawString(doc.leftMargin, 8 * mm, t("reports.export.generated_by"))
    canvas.drawCentredString(
        width / 2,
        8 * mm,
        FLOWCORE_CONTACT_PHONE,
    )
    canvas.drawRightString(
        width - doc.rightMargin,
        8 * mm,
        t("reports.export.page", page=doc.page),
    )
    canvas.restoreState()


PRODUCT_IMAGE_PLACEHOLDER = PROJECT_ROOT / "images" / "products" / "_placeholder.png"


def resolve_product_image_path(image_url: str | None) -> Path:
    """Resolve a product image URL/path to an existing file, else placeholder."""
    raw = (image_url or "").strip().replace("\\", "/")
    if raw.startswith("/"):
        raw = raw[1:]
    if raw:
        path = PROJECT_ROOT / raw
        if path.exists():
            return path
    return PRODUCT_IMAGE_PLACEHOLDER


def _product_image_flowable(image_url: str | None, *, size_mm: float = 12) -> Any:
    path = resolve_product_image_path(image_url)
    size = size_mm * mm
    if path.exists():
        return Image(str(path), width=size, height=size)
    # Empty-looking box when placeholder is missing
    box = Table([[""]], colWidths=[size], rowHeights=[size])
    box.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, FC_BORDER),
                ("BACKGROUND", (0, 0), (-1, -1), FC_BG),
            ]
        )
    )
    return box


def _build_document_header(
    *,
    document: SimpleDocTemplate,
    styles: dict[str, ParagraphStyle],
    report_title: str,
    date_from: str | None = None,
    date_to: str | None = None,
    include_period: bool = True,
) -> list[Any]:
    settings = load_settings_values()
    company_name = settings.get("company_name") or "FlowCore"
    company_address = settings.get("company_address") or ""
    company_phone = settings.get("company_phone") or ""
    story: list[Any] = []

    logo_path = _resolve_logo_file()
    company_lines: list[Any] = [Paragraph(company_name, styles["company"])]
    if company_address:
        company_lines.append(Paragraph(company_address, styles["meta"]))
    if company_phone:
        company_lines.append(Paragraph(company_phone, styles["meta"]))

    company_table = Table(
        [[line] for line in company_lines],
        colWidths=[document.width - 40 * mm],
    )
    company_table.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )

    if logo_path is not None:
        logo_max = 18 * mm
        logo = Image(str(logo_path), width=logo_max, height=logo_max)
        header_table = Table(
            [[logo, company_table]],
            colWidths=[24 * mm, document.width - 24 * mm],
        )
        header_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (0, 0), 6),
                    ("RIGHTPADDING", (1, 0), (1, 0), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        story.append(header_table)
    else:
        story.append(company_table)

    story.append(Spacer(1, 4 * mm))
    accent = Table([[""]], colWidths=[document.width])
    accent.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), FC_SURFACE_2),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(accent)
    story.append(Spacer(1, 3 * mm))

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    story.append(Paragraph(report_title, styles["title"]))
    story.append(
        Paragraph(t("reports.export.generated_date", date=generated_at), styles["meta"])
    )
    if include_period:
        if date_from or date_to:
            period = f"{date_from or '…'} — {date_to or '…'}"
        else:
            period = t("reports.export.period_empty")
        story.append(
            Paragraph(t("reports.export.report_period", period=period), styles["meta"])
        )
    story.append(Spacer(1, 4 * mm))
    return story


def _styled_data_table(
    *,
    document: SimpleDocTemplate,
    styles: dict[str, ParagraphStyle],
    columns: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    image_size_mm: float = 12,
) -> Table:
    export_columns = _export_columns(columns)
    header_cells = [
        Paragraph(str(column.get("label") or column.get("field") or ""), styles["header_cell"])
        for column in export_columns
    ]
    table_data: list[list[Any]] = [header_cells]
    aligns = [
        _column_align(column, str(column.get("field") or ""))
        for column in export_columns
    ]

    for row in rows:
        cells: list[Any] = []
        for column, align in zip(export_columns, aligns):
            field = str(column.get("field") or "")
            if field in {"image_url", "image", "product_image"}:
                cells.append(_product_image_flowable(row.get("image_url") or row.get(field), size_mm=image_size_mm))
                continue
            text = _format_cell(row.get(field, ""), field)
            cells.append(
                Paragraph(text.replace("\n", "<br/>"), _body_style_for(styles, align))
            )
        table_data.append(cells)

    usable = document.width
    weights: list[float] = []
    for column in export_columns:
        field = str(column.get("field") or "")
        if field in {"image_url", "image", "product_image"}:
            weights.append(0.7)
        elif field in {
            "product",
            "name",
            "customer",
            "supplier",
            "sale_number",
            "purchase_number",
            "description",
        }:
            weights.append(1.8)
        elif field in _CURRENCY_FIELDS or field in _NUMERIC_FIELDS:
            weights.append(1.0)
        else:
            weights.append(1.2)
    weight_sum = sum(weights) or 1.0
    col_widths = [usable * (w / weight_sum) for w in weights]

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    style_commands: list[tuple[Any, ...]] = [
        ("BACKGROUND", (0, 0), (-1, 0), FC_PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), _FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, FC_BORDER),
        ("BOX", (0, 0), (-1, -1), 0.8, FC_PRIMARY),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [FC_SURFACE, FC_BG]),
    ]
    for index, align in enumerate(aligns):
        field = str(export_columns[index].get("field") or "")
        if field in {"image_url", "image", "product_image"}:
            style_commands.append(("ALIGN", (index, 1), (index, -1), "CENTER"))
        else:
            style_commands.append(("ALIGN", (index, 1), (index, -1), align.upper()))
    table.setStyle(TableStyle(style_commands))
    return table


def build_report_pdf(
    *,
    report_title: str,
    columns: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    date_from: str | None = None,
    date_to: str | None = None,
) -> bytes:
    """Build a styled PDF for the currently displayed report."""
    styles = _build_styles()
    settings = load_settings_values()
    company_name = settings.get("company_name") or "FlowCore"

    export_columns = _export_columns(columns)
    page_size = landscape(A4) if len(export_columns) > 6 else A4
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=page_size,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=18 * mm,
        title=report_title,
        author=company_name,
    )

    story = _build_document_header(
        document=document,
        styles=styles,
        report_title=report_title,
        date_from=date_from,
        date_to=date_to,
        include_period=True,
    )

    if not export_columns:
        story.append(Paragraph(t("reports.export.no_columns"), styles["meta"]))
    else:
        story.append(
            _styled_data_table(
                document=document,
                styles=styles,
                columns=export_columns,
                rows=rows,
            )
        )

    document.build(
        story,
        onFirstPage=_add_page_decorations,
        onLaterPages=_add_page_decorations,
    )
    return buffer.getvalue()


def build_catalog_pdf(
    *,
    report_title: str,
    columns: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    landscape_orientation: bool = True,
) -> bytes:
    """Build a product catalog/price-list PDF using the report PDF styling."""
    styles = _build_styles()
    settings = load_settings_values()
    company_name = settings.get("company_name") or "FlowCore"
    export_columns = _export_columns(columns)
    page_size = landscape(A4) if landscape_orientation else A4
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=page_size,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=18 * mm,
        title=report_title,
        author=company_name,
    )

    story = _build_document_header(
        document=document,
        styles=styles,
        report_title=report_title,
        include_period=False,
    )

    if not export_columns:
        story.append(Paragraph(t("reports.export.no_columns"), styles["meta"]))
    else:
        story.append(
            _styled_data_table(
                document=document,
                styles=styles,
                columns=export_columns,
                rows=rows,
                image_size_mm=11,
            )
        )

    document.build(
        story,
        onFirstPage=_add_page_decorations,
        onLaterPages=_add_page_decorations,
    )
    return buffer.getvalue()


def save_report_pdf(
    content: bytes,
    *,
    report_type: str,
) -> Path:
    """Persist PDF under exports/ and return the path."""
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_type = (report_type or "report").strip().lower().replace(" ", "_") or "report"
    path = EXPORTS_DIR / f"{safe_type}_{stamp}.pdf"
    path.write_bytes(content)
    return path