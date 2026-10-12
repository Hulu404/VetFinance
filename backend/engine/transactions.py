"""Operations screen: month summary and the explanatory Figures and texts (all built from the data,
by templates; nothing here calls a network or a model)."""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from engine.figure import Figure, FigureItem, ordered_sources
from engine.money import format_rub
from engine.ru import format_date, format_date_short, month_name, plural

UNCATEGORISED = "Без статьи"
NO_OPERATIONS = "Нет операций"
SOURCE_LABELS = {
    "bank": "Выписка банка",
    "vetmanager": "Ветменеджер",
    "bot": "Бот",
    "manual": "Внесено вручную",
}
SOURCE_NAMES = {"bank": "Банк", "vetmanager": "Ветменеджер", "bot": "Бот", "manual": "Вручную"}


@dataclass(frozen=True)
class SummaryResult:
    income: Figure
    expense: Figure
    balance: Figure


def _in_month(day: date, month: str) -> bool:
    return day.strftime("%Y-%m") == month


def _month_title(month: str) -> str:
    year, number = month.split("-")
    return month_name(int(year), int(number))


def _breakdown(totals: Mapping[str, int]) -> tuple[FigureItem, ...]:
    """By category, the biggest first; the uncategorised line goes last."""
    items = sorted(totals.items(), key=lambda kv: (kv[0] == UNCATEGORISED, -kv[1], kv[0]))
    return tuple(FigureItem(label=label, value=value) for label, value in items) or (
        FigureItem(label=NO_OPERATIONS, value=0),
    )


def _sources(rows: Iterable[Mapping[str, Any]]) -> tuple[str, ...]:
    return ordered_sources({str(r["source"]) for r in rows}) or ("manual",)


def summarize(transactions: Sequence[Mapping[str, Any]], month: str) -> SummaryResult:
    """Income, expense and the month balance (income minus expense) for `month` (YYYY-MM).

    Included: kind in/out with status ok or check; excluded: duplicates and transfers. Operations
    without a category are shown as "Без статьи".
    """
    income: dict[str, int] = {}
    expense: dict[str, int] = {}
    in_rows: list[Mapping[str, Any]] = []
    out_rows: list[Mapping[str, Any]] = []
    for row in transactions:
        if row["status"] == "duplicate" or row["kind"] == "transfer":
            continue
        if not _in_month(row["date"], month):
            continue
        label = row.get("category") or UNCATEGORISED
        if row["kind"] == "in":
            income[label] = income.get(label, 0) + row["amount"]
            in_rows.append(row)
        elif row["kind"] == "out":
            expense[label] = expense.get(label, 0) - row["amount"]
            out_rows.append(row)
    total_in, total_out = sum(income.values()), sum(expense.values())
    title = _month_title(month)
    scope = "операции со статусами «учтено» и «на проверку», без дублей и переводов между счетами"
    return SummaryResult(
        income=Figure(
            total_in, "rub", _breakdown(income), _sources(in_rows), f"Доходы за {title}: {scope}."
        ),
        expense=Figure(
            total_out,
            "rub",
            _breakdown(expense),
            _sources(out_rows),
            f"Расходы за {title}: {scope}.",
        ),
        balance=Figure(
            value=total_in - total_out,
            unit="rub",
            breakdown=(FigureItem("Доходы", total_in), FigureItem("Расходы", -total_out)),
            source=_sources(in_rows + out_rows),
            note=(
                f"Сальдо за {title}: доходы минус расходы. Это не остаток на счетах; "
                "переводы между своими счетами не входят."
            ),
        ),
    )


def transaction_figure(
    *,
    amount: int,
    op_date: date,
    source: str,
    account_name: str,
    kind: str,
    status: str,
    category_source: str | None,
    category_name: str | None,
    rule_name: str | None,
) -> Figure:
    """The tooltip of an operation amount: where it came from and why it has its category."""
    label = f"{SOURCE_LABELS.get(source, source)} · {account_name}"
    parts = [f"Операция от {format_date(op_date)}, счёт «{account_name}»."]
    if kind == "transfer":
        parts.append("Перевод между своими счетами: в доходы и расходы не входит.")
    elif category_name is None:
        parts.append("Статьи пока нет: операция ждёт проверки.")
    elif category_source == "rule":
        parts.append(
            f"Статья «{category_name}» назначена правилом"
            + (f" «{rule_name}»." if rule_name else ".")
        )
    elif category_source == "manual":
        parts.append(f"Статья «{category_name}» выбрана вручную.")
    else:
        parts.append(f"Статья «{category_name}».")
    if status == "duplicate":
        parts.append("Дубль другой операции: не входит в остаток и отчёты.")
    return Figure(
        value=amount,
        unit="rub",
        breakdown=(FigureItem(label=label, value=amount),),
        source=(source,),
        note=" ".join(parts),
    )


def _dates_phrase(first: date, second: date) -> str:
    if first == second:
        return f"дата {format_date_short(first)}"
    low, high = sorted((first, second))
    if low.month == high.month:
        return f"даты {low.day} и {format_date_short(high)}"
    return f"даты {format_date_short(low)} и {format_date_short(high)}"


def duplicate_reason(amount: int, first: date, second: date) -> str:
    """Why two operations look like one payment (template for the Duplicates tab)."""
    return f"одинаковая сумма {format_rub(abs(amount))}, {_dates_phrase(first, second)}, разные источники"


def suggestion_text(reason: str, count: int, counterparty: str) -> str:
    """The continuation of "Предлагаем «статья»:" shown next to an uncategorised operation."""
    who = f"«{counterparty}»" if counterparty else "этому контрагенту"
    if reason == "rule":
        return f"по правилу для {who}"
    word = plural(count, "операция", "операции", "операций")
    verb = plural(count, "разнесена", "разнесено", "разнесено")
    target = f"по {who}" if counterparty else "по этому контрагенту"
    return f"так же {verb} {count} {word} {target}"
