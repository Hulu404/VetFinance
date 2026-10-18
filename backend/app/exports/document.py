"""Format-neutral document of a report export and the builders that fill it from the API models.

The file is built from the same API model that the JSON endpoint returns (never from a second calculation),
so every number in Excel and PDF is the `Figure.value` of the screen. Money cells hold kopecks (the
renderers show roubles), percent cells hold percent units.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.schemas import FigureOut
from app.schemas_reports import IdleItemOut, NormOut, PnlOut, StockOut
from engine.ru import MONTHS_NOMINATIVE, format_day_month

BRAND = "ВетФинанс"
SOURCE_NAMES = {
    "bank": "Банк",
    "vetmanager": "Ветменеджер",
    "bot": "Бот",
    "manual": "Вручную",
    "calc": "Расчёт",
}
REASON_TEXTS = {
    "no_vetmanager": "Нет данных Ветменеджера за месяц: выручка равна нулю.",
    "bank_gap": "Выписки банка покрывают период не целиком.",
    "short_period": "С начала месяца прошло меньше 7 дней.",
    "no_obligations": "Обязательства и амортизация не заполнены.",
    "no_benchmark": "Нормы для клиники нет.",
    "missing_expiry": "У части партий нет срока годности.",
    "short_history": "История склада короткая.",
    "stale_stock": "Остатки склада давно не обновлялись.",
}
STATUS_WORDS = {
    "ok": "в норме",
    "above": "выше нормы",
    "below": "ниже нормы",
    "no_norm": "нормы нет",
}
REASON_WORDS = {"expired": "Истёк срок годности", "damaged": "Брак и бой", "other": "Другое"}
KIND_BOLD = frozenset({"subtotal", "total"})


@dataclass(frozen=True)
class Rub:
    kopecks: int


@dataclass(frozen=True)
class Pct:
    value: float  # percent units: 11.7 means 11,7%


@dataclass(frozen=True)
class Pp:
    value: float  # percentage points: the deviation from the border of the norm


@dataclass(frozen=True)
class Days:
    value: int


Cell = str | int | date | Rub | Pct | Pp | Days | None


@dataclass(frozen=True)
class Row:
    cells: tuple[Cell, ...]
    bold: bool = False
    indent: int = 0


@dataclass(frozen=True)
class Table:
    title: str
    columns: tuple[str, ...]
    rows: tuple[Row, ...]
    widths: tuple[int, ...]  # relative column widths


@dataclass(frozen=True)
class FigureRef:
    label: str
    figure: FigureOut


@dataclass(frozen=True)
class Document:
    report: str  # pnl | norm | stock
    title: str
    clinic: str
    period_line: str
    made_at: str
    data_as_of: str | None
    headline: str | None
    reasons: tuple[str, ...]
    tables: tuple[Table, ...]
    figures: tuple[FigureRef, ...]
    footnotes: tuple[str, ...]


def month_title(month: str) -> str:
    """'Сентябрь 2026' for '2026-09'."""
    name = MONTHS_NOMINATIVE[int(month[5:7]) - 1]
    return f"{name.capitalize()} {month[:4]}"


def period_text(month: str, status: str, to: date | None) -> str:
    if status == "open" and to is not None:
        return f"{month_title(month)} · месяц идёт, данные по {format_day_month(to)}"
    return f"{month_title(month)} · месяц закрыт"


def reason_texts(reasons: list[str]) -> tuple[str, ...]:
    return tuple(REASON_TEXTS.get(r, r) for r in reasons)


def cell_of(value: int | float, unit: str) -> Cell:
    if unit == "rub":
        return Rub(int(value))
    if unit in ("pct", "pp"):
        return Pct(float(value))
    return int(value)


def sources_text(figure: FigureOut) -> str:
    return ", ".join(SOURCE_NAMES.get(s, s) for s in figure.source)


# ------------------------------------------------------------------ P&L
def _pnl_main(model: PnlOut) -> Table:
    rows: list[Row] = []
    for r in model.rows:
        share = Pct(float(r.share_pct.value)) if r.share_pct is not None else None
        rows.append(Row((r.label, Rub(int(r.amount.value)), share), bold=r.kind in KIND_BOLD))
        for child in r.children or []:
            c_share = Pct(float(child.share_pct.value)) if child.share_pct is not None else None
            rows.append(Row((child.label, Rub(int(child.amount.value)), c_share), indent=1))
    return Table("Вся клиника", ("Статья", "Сумма, ₽", "Доля выручки, %"), tuple(rows), (6, 3, 3))


def _pnl_directions(model: PnlOut) -> Table:
    columns = (
        "Направление",
        "Выручка, ₽",
        "Доля выручки, %",
        "Прямые расходы, ₽",
        "Маржа, ₽",
        "Маржа, % выручки направления",
    )
    rows = [
        Row(
            (
                d.label,
                Rub(int(d.revenue.value)),
                Pct(float(d.revenue_share_pct.value)),
                Rub(int(d.direct_costs.value)),
                Rub(int(d.margin.value)),
                Pct(float(d.margin_pct.value)),
            )
        )
        for d in model.directions or []
    ]
    if model.common_variable is not None:
        rows.append(
            Row(
                (
                    "Общие переменные расходы",
                    None,
                    None,
                    Rub(int(model.common_variable.value)),
                    None,
                    None,
                )
            )
        )
    marginal = next(r for r in model.rows if r.key == "marginal_profit")
    rows.append(
        Row(
            (
                "Маржинальная прибыль клиники",
                None,
                None,
                None,
                Rub(int(marginal.amount.value)),
                None,
            ),
            bold=True,
        )
    )
    return Table("Услуги и товары", columns, tuple(rows), (4, 3, 3, 3, 3, 3))


def pnl_document(model: PnlOut, clinic: str, made_at: str, data_as_of: str | None) -> Document:
    """The P&L always holds both modes (clinic and services/goods); `model` is the direction view."""
    figures: list[FigureRef] = []
    for r in model.rows:
        figures.append(FigureRef(r.label, r.amount))
        figures.extend(FigureRef(c.label, c.amount) for c in r.children or [])
    for d in model.directions or []:
        figures.append(FigureRef(f"{d.label}: прямые расходы", d.direct_costs))
        figures.append(FigureRef(f"{d.label}: маржа", d.margin))
    if model.common_variable is not None:
        figures.append(FigureRef("Общие переменные расходы", model.common_variable))
    net = next(r for r in model.rows if r.key == "net_profit")
    notes = [net.amount.note]
    if model.period.status == "open" and model.period.to is not None:
        notes.append(
            "Месяц ещё идёт: обязательства и амортизация взяты за весь месяц, налоги — только "
            f"уплаченные на {format_day_month(model.period.to)}. К концу месяца прибыль изменится."
        )
    return Document(
        report="pnl",
        title="Прибыль и убытки",
        clinic=clinic,
        period_line=period_text(model.period.month, model.period.status, model.period.to),
        made_at=made_at,
        data_as_of=data_as_of,
        headline=model.headline,
        reasons=reason_texts(list(model.partial_reasons)),
        tables=(_pnl_main(model), _pnl_directions(model)),
        figures=tuple(figures),
        footnotes=tuple(notes),
    )


# ------------------------------------------------------------------ norm
def _norm_table(model: NormOut) -> Table:
    columns = (
        "Статья",
        "Сумма, ₽",
        "Доля выручки, %",
        "Норма от, %",
        "Норма до, %",
        "Статус",
        "Отклонение, п.п.",
        "Отклонение, ₽",
    )
    rows: list[Row] = []
    revenue = 0
    for i in model.items:
        amount = sum(int(b.value) for b in i.actual_pct.breakdown)
        revenue = revenue or next((int(d.value) for d in i.actual_pct.details or []), 0)
        low = Pct(i.norm.min_pct) if i.norm and i.norm.min_pct is not None else None
        high = Pct(i.norm.max_pct) if i.norm and i.norm.max_pct is not None else None
        status = STATUS_WORDS.get(i.status or "", None)
        if status and i.memo:
            status += " (справочно)"
        rows.append(
            Row(
                (
                    i.label,
                    Rub(amount),
                    Pct(float(i.actual_pct.value)),
                    low,
                    high,
                    status,
                    Pp(float(i.deviation_pp.value)) if i.deviation_pp else None,
                    Rub(int(i.deviation_rub.value)) if i.deviation_rub else None,
                ),
                bold=i.kind == "profit",
            )
        )
    if model.items:
        rows.append(
            Row(
                ("Выручка месяца", Rub(revenue), Pct(100.0), None, None, None, None, None),
                bold=True,
            )
        )
    return Table("Норма", columns, tuple(rows), (6, 3, 3, 2, 2, 3, 3, 3))


def norm_document(model: NormOut, clinic: str, made_at: str, data_as_of: str | None) -> Document:
    figures: list[FigureRef] = []
    for i in model.items:
        figures.append(FigureRef(f"{i.label}: доля", i.actual_pct))
        if i.deviation_pp is not None:
            figures.append(FigureRef(f"{i.label}: отклонение, п.п.", i.deviation_pp))
        if i.deviation_rub is not None:
            figures.append(FigureRef(f"{i.label}: отклонение, ₽", i.deviation_rub))
    notes = [
        "Источник нормы: ветклиники на 2–6 врачей. Оценка по прототипу, заменим данными отраслевых опросов."
    ]
    if any(i.memo for i in model.items):
        notes.append("Списание по сроку справочное: в сумму долей не входит.")
    if model.period.status == "open":
        notes.append("Месяц ещё идёт: с нормой доли не сравниваются, статусы и отклонения пусты.")
    return Document(
        report="norm",
        title="Норма",
        clinic=clinic,
        period_line=period_text(model.period.month, model.period.status, model.period.to),
        made_at=made_at,
        data_as_of=data_as_of,
        headline=model.headline,
        reasons=reason_texts(list(model.partial_reasons)),
        tables=(_norm_table(model),),
        figures=tuple(figures),
        footnotes=tuple(notes),
    )


# ------------------------------------------------------------------ stock
def _summary(model: StockOut) -> Table:
    pos = next((int(d.value) for d in model.stock_value.details or []), 0)
    rows = (
        Row(("Остаток на складе по закупочной цене, ₽", Rub(int(model.stock_value.value)))),
        Row(("Позиций на складе", pos)),
        Row(("Без движения от 60 дней, ₽", Rub(int(model.frozen.value)))),
        Row(("Позиций без движения", int(model.frozen_positions.value))),
        Row(("Срок годности истекает за 60 дней, ₽", Rub(int(model.expiring_60d.value)))),
        Row(("Просрочено на полке, ₽", Rub(int(model.expired_on_hand.value)))),
        Row(
            (
                f"Списано за {month_title(model.month).lower()}, ₽",
                Rub(int(model.written_off_month.value)),
            )
        ),
        Row(("Норма списания по сроку, ₽", Rub(int(model.written_off_norm.value)))),
        Row(("Оборачиваемость склада, дней", int(model.turnover_days.value))),
        Row(("Норма оборачиваемости, дней", model.norm_turnover_days)),
    )
    return Table("Сводка", ("Показатель", "Значение"), rows, (8, 3))


def _expiry_table(title: str, rows: list[Any]) -> Table:
    # a number never stands right before an amount: the text of a PDF is checked by squeezing spaces
    body = tuple(
        Row((r.item, r.qty, r.expires_on, Days(r.days_left), Rub(int(r.amount.value))))
        for r in rows
    )
    columns = ("Позиция", "Количество", "Срок годности", "Осталось дней", "Сумма, ₽")
    return Table(title, columns, body, (6, 3, 3, 3, 3))


def _idle_table(items: list[IdleItemOut]) -> Table:
    labels = {"60_89": "60–89 дней", "90_179": "90–179 дней", "180_plus": "От 180 дней"}
    body = tuple(
        Row(
            (
                i.item,
                i.qty,
                i.last_movement_on,
                Days(i.idle_days),
                Rub(int(i.amount.value)),
                labels[i.bucket],
            )
        )
        for i in items
    )
    columns = (
        "Позиция",
        "Количество",
        "Последнее движение",
        "Дней без движения",
        "Сумма, ₽",
        "Интервал",
    )
    return Table("Без движения", columns, body, (6, 3, 3, 3, 3, 3))


def _writeoff_table(model: StockOut) -> Table:
    body = tuple(
        Row((w.item, w.date, w.qty, REASON_WORDS.get(w.reason, w.reason), Rub(int(w.amount.value))))
        for w in model.written_off_items
    )
    return Table(
        "Списания", ("Позиция", "Дата", "Количество", "Причина", "Сумма, ₽"), body, (6, 3, 3, 4, 3)
    )


def stock_document(
    model: StockOut, idle: list[IdleItemOut], clinic: str, made_at: str, data_as_of: str | None
) -> Document:
    figures = (
        FigureRef("Остаток на складе", model.stock_value),
        FigureRef("Без движения от 60 дней", model.frozen),
        FigureRef("Позиций без движения", model.frozen_positions),
        FigureRef("Срок годности истекает за 60 дней", model.expiring_60d),
        FigureRef("Просрочено на полке", model.expired_on_hand),
        FigureRef("Списано за месяц", model.written_off_month),
        FigureRef("Норма списания", model.written_off_norm),
        FigureRef("Оборачиваемость", model.turnover_days),
    )
    tables = [_summary(model)]
    for title, rows in (("Срок годности", model.expiring), ("Просрочено", model.expired_items)):
        if rows:
            tables.append(_expiry_table(title, list(rows)))
    if idle:
        tables.append(_idle_table(idle))
    if model.written_off_items:
        tables.append(_writeoff_table(model))
    return Document(
        report="stock",
        title="Склад и сроки",
        clinic=clinic,
        period_line=f"Остатки на {model.as_of.strftime('%d.%m.%Y')}; списания: {month_title(model.month).lower()}",
        made_at=made_at,
        data_as_of=data_as_of,
        headline=model.headline,
        reasons=reason_texts(list(model.partial_reasons)),
        tables=tuple(tables),
        figures=figures,
        footnotes=(
            "Остатки оценены по закупочной цене партий. Оборачиваемость: запас × 90 ÷ расход за 90 дней.",
        ),
    )
