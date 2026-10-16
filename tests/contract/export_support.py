"""Readers and checkers for report exports (function 20): xlsx is parsed and compared with the JSON of the report endpoint,
pdf is compared by its text. No product logic here: the numbers come from the JSON the same endpoint returns.

Layout rules the checks rely on (proposal to backend, docs/handoff.md "tester -> backend-developer (этап 3)"):
- xlsx: money cells are NUMBERS in roubles (kopecks / 100, two decimals), never text; percent cells are numbers in percent
  units (12.3 means 12,3%); a report row is found by its label in a text cell of the row, its numbers are the numeric cells of the
  same row. The first sheet holds the report; extra sheets are allowed.
- pdf: text contains every row label and every amount as "1 234 567,89" (any kind of space, "₽" optional, ",00" optional for whole roubles).
"""
import io
import re
from decimal import Decimal

SPACES = re.compile("[   \\s]")
MINUS = "−"


# ------------------------------------------------------------------ xlsx
def load_xlsx(content: bytes):
    import pytest
    openpyxl = pytest.importorskip("openpyxl", reason="openpyxl is not installed (pip install -r tests/contract/requirements.txt)")
    return openpyxl.load_workbook(io.BytesIO(content), data_only=True)


def sheet_rows(wb, first_sheet_only=True):
    sheets = wb.worksheets[:1] if first_sheet_only else wb.worksheets
    for ws in sheets:
        for row in ws.iter_rows(values_only=True):
            yield list(row)


def find_row(rows, label: str):
    """First row that has a text cell equal to the label (whitespace-normalised)."""
    want = SPACES.sub(" ", label).strip()
    for row in rows:
        for cell in row:
            if isinstance(cell, str) and SPACES.sub(" ", cell).strip() == want:
                return row
    return None


def numbers(row):
    return [c for c in row if isinstance(c, (int, float, Decimal)) and not isinstance(c, bool)]


def row_has_money(row, kopecks: int) -> bool:
    return any(round(Decimal(str(c)) * 100) == kopecks for c in numbers(row))


def row_has_pct(row, value) -> bool:
    return any(abs(float(c) - float(value)) <= 0.05 for c in numbers(row))


def all_numbers(wb):
    out = []
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            out.extend(numbers(list(row)))
    return out


def workbook_has_money(wb, kopecks: int) -> bool:
    return any(round(Decimal(str(c)) * 100) == kopecks for c in all_numbers(wb))


def text_cells(wb):
    return [c for ws in wb.worksheets for row in ws.iter_rows(values_only=True) for c in row if isinstance(c, str)]


# ------------------------------------------------------------------ pdf
def pdf_text(content: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            import pytest
            pytest.skip("pypdf / PyPDF2 is not installed (pip install -r tests/contract/requirements.txt)")
    reader = PdfReader(io.BytesIO(content))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def normalise(text: str) -> str:
    return SPACES.sub(" ", text).replace(MINUS, "-")


def pdf_has_amount(text: str, kopecks: int) -> bool:
    squeezed = SPACES.sub("", text)
    rub, kop = divmod(abs(kopecks), 100)
    body = f"{rub}" + (f",{kop:02d}" if kop else "(?:,00)?")
    return re.search(r"(?<![\d,])" + body + r"(?!\d|,\d)", squeezed) is not None


def pdf_has_pct(text: str, value) -> bool:
    shown = f"{abs(float(value)):.1f}".replace(".", ",")
    squeezed = SPACES.sub("", text)
    return re.search(r"(?<![\d,])" + re.escape(shown) + r"(?!\d)", squeezed) is not None


def pdf_has_label(text: str, label: str) -> bool:
    return SPACES.sub("", label).lower() in SPACES.sub("", text).lower()
