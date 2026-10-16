"""PDF of a report: A4 portrait, the Onest font (Cyrillic and the rouble sign are embedded), a plain table.

No colours by tone, no scales, no personal data. The brand is the text "ВетФинанс" in the accent colour.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

from fpdf import FPDF
from fpdf.fonts import FontFace

from app.exports.document import (
    BRAND,
    Cell,
    Days,
    Document,
    Pct,
    Pp,
    Rub,
    Table,
    cell_of,
    sources_text,
)
from engine.money import format_pct

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
FONT_NAME = "Onest"
ACCENT = (138, 15, 58)  # --color-accent-dark
INK = (31, 31, 36)
SOFT = (110, 110, 120)
MARGIN = 14
MINUS = "−"
RUB_SIGN = "₽"
EM_DASH = "—"
SMALL = 8
BODY = 10
PAGE_WIDTH = 210


def _rub(kopecks: int) -> str:
    sign = MINUS if kopecks < 0 else ""
    rub, kop = divmod(abs(kopecks), 100)
    return f"{sign}{rub:,}".replace(",", " ") + f",{kop:02d}"


def _text(value: Cell) -> str:
    if value is None:
        return EM_DASH
    if isinstance(value, Rub):
        return f"{_rub(value.kopecks)} {RUB_SIGN}"
    if isinstance(value, Pct):
        return f"{format_pct(Decimal(str(value.value)))}%"
    if isinstance(value, Pp):
        return f"{format_pct(Decimal(str(value.value)))} п.п."
    if isinstance(value, Days):
        return f"{str(value.value).replace('-', MINUS)} дн."
    if isinstance(value, date):
        return value.strftime("%d.%m.%Y")
    return str(value)


def _alignment(columns: int, first_text: bool = True) -> tuple[str, ...]:
    return ("LEFT",) + ("RIGHT",) * (columns - 1) if first_text else ("RIGHT",) * columns


def _make_pdf() -> FPDF:
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.add_font(FONT_NAME, "", str(FONT_DIR / "Onest-Regular.ttf"))
    pdf.add_font(FONT_NAME, "B", str(FONT_DIR / "Onest-SemiBold.ttf"))
    pdf.set_margins(MARGIN, MARGIN, MARGIN)
    pdf.set_auto_page_break(auto=True, margin=MARGIN)
    pdf.set_title("ВетФинанс")
    pdf.add_page()
    return pdf


def _paragraph(
    pdf: FPDF, text: str, size: int = BODY, *, bold: bool = False, color: tuple[int, int, int] = INK
) -> None:
    pdf.set_font(FONT_NAME, "B" if bold else "", size)
    pdf.set_text_color(*color)
    pdf.multi_cell(0, size * 0.5, text, new_x="LMARGIN", new_y="NEXT")


def _header(pdf: FPDF, doc: Document) -> None:
    _paragraph(pdf, BRAND, 16, bold=True, color=ACCENT)
    _paragraph(pdf, doc.clinic, BODY)
    pdf.ln(1)
    _paragraph(pdf, f"{doc.title} · {doc.period_line}", 13, bold=True)
    _paragraph(
        pdf,
        f"Сформировано: {doc.made_at}. Данные на: {doc.data_as_of or 'нет данных'}.",
        SMALL,
        color=SOFT,
    )
    pdf.ln(2)
    if doc.headline:
        _paragraph(pdf, doc.headline, 11, bold=True)
        pdf.ln(1)
    for reason in doc.reasons:
        _paragraph(pdf, f"Внимание: {reason}", SMALL, color=ACCENT)


def _table(pdf: FPDF, table: Table, *, title: bool) -> None:
    pdf.ln(2)
    if title:
        _paragraph(pdf, table.title, 11, bold=True)
    pdf.set_font(FONT_NAME, "", SMALL)
    pdf.set_text_color(*INK)
    total = sum(table.widths)
    usable = PAGE_WIDTH - 2 * MARGIN
    widths = tuple(round(usable * w / total, 2) for w in table.widths)
    head = FontFace(emphasis="BOLD", fill_color=(248, 225, 233))
    with pdf.table(
        col_widths=widths,
        text_align=_alignment(len(table.columns)),
        line_height=4.6,
        headings_style=head,
        borders_layout="HORIZONTAL_LINES",
        padding=1,
    ) as pdf_table:
        header = pdf_table.row()
        for column in table.columns:
            header.cell(column)
        for row in table.rows:
            line = pdf_table.row()
            style = FontFace(emphasis="BOLD") if row.bold else None
            for index, value in enumerate(row.cells):
                text = _text(value)
                if index == 0 and row.indent:
                    text = "    " * row.indent + text
                line.cell(text, style=style)


def _composition(pdf: FPDF, doc: Document) -> None:
    pdf.ln(3)
    _paragraph(pdf, "Состав и источники", 11, bold=True)
    for ref in doc.figures:
        fig = ref.figure
        _paragraph(pdf, f"{ref.label}: {_text(cell_of(fig.value, fig.unit))}", SMALL, bold=True)
        parts = [f"{b.label} {_text(cell_of(b.value, b.unit))}" for b in fig.breakdown]
        if parts:
            _paragraph(pdf, "; ".join(parts), SMALL, color=SOFT)
        _paragraph(pdf, f"{fig.note} Источники: {sources_text(fig)}.", SMALL, color=SOFT)


def render_pdf(doc: Document) -> bytes:
    pdf = _make_pdf()
    _header(pdf, doc)
    for index, table in enumerate(doc.tables):
        _table(pdf, table, title=index > 0 or len(doc.tables) > 1)
    for note in doc.footnotes:
        pdf.ln(1)
        _paragraph(pdf, note, SMALL, color=SOFT)
    _composition(pdf, doc)
    return bytes(pdf.output())
