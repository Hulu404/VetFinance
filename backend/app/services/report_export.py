"""Excel and PDF files of the reports, built from the same models as the JSON endpoints."""

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from starlette.concurrency import run_in_threadpool

from app.exports.document import Document, norm_document, pnl_document, stock_document
from app.exports.pdf import render_pdf
from app.exports.xlsx import render_xlsx
from app.repo import Repository
from app.services import reports as service

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF_TYPE = "application/pdf"


@dataclass(frozen=True)
class ExportFile:
    content: bytes
    media_type: str
    filename: str


def _local(moment: datetime, timezone: str) -> str:
    return moment.astimezone(ZoneInfo(timezone)).strftime("%d.%m.%Y %H:%M")


async def _document(repo: Repository, window: service.Window, name: str, now: datetime) -> Document:
    clinic = await repo.get_clinic()
    made_at = _local(now, clinic.timezone)
    data_at = await repo.last_data_at()
    data_as_of = _local(data_at, clinic.timezone) if data_at else None
    if name == "pnl":
        model = await service.build_pnl(repo, window, "direction")
        return pnl_document(model, clinic.name, made_at, data_as_of)
    if name == "norm":
        return norm_document(
            await service.build_norm(repo, window), clinic.name, made_at, data_as_of
        )
    stock = await service.build_stock(repo, window)
    idle = await service.build_full_idle(repo, window)
    return stock_document(stock, idle, clinic.name, made_at, data_as_of)


async def build_export(
    repo: Repository, window: service.Window, name: str, fmt: str, now: datetime
) -> ExportFile:
    doc = await _document(repo, window, name, now)
    month = window.as_of.strftime("%Y-%m") if name == "stock" else window.month.strftime("%Y-%m")
    render, media_type = (render_xlsx, XLSX_TYPE) if fmt == "xlsx" else (render_pdf, PDF_TYPE)
    content = await run_in_threadpool(render, doc)
    return ExportFile(content, media_type, f"vetfinance-{name}-{month}.{fmt}")
