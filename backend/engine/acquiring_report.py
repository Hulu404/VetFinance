"""Reconciliation rows and totals for the screen, as Figures with breakdown and source.

Takes the day results of `reconcile_acquiring`, joins the days closed by one credit into one row and
builds every number the screen shows. All sums are computed here (rule 1 of CLAUDE.md).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from engine.acquiring import WAITING, DayResult
from engine.figure import Figure, FigureItem
from engine.money import rate_bp_to_pct
from engine.ru import format_date_short, format_day_month, format_range_short

SOURCE_CARD = ("vetmanager",)
SOURCE_BANK = ("bank",)
SOURCE_BOTH = ("bank", "vetmanager")


@dataclass(frozen=True)
class MemberView:
    day: date
    card_payments: Figure
    commission: Figure
    expected: Figure


@dataclass(frozen=True)
class RowView:
    date_from: date
    date_to: date
    card_payments: Figure
    commission: Figure
    expected: Figure
    credited: Figure | None
    discrepancy: Figure | None
    status: str
    expected_by: date
    members: tuple[MemberView, ...]
    credit_id: str | None


@dataclass(frozen=True)
class SummaryView:
    card_payments: Figure
    commission: Figure
    credited: Figure
    discrepancy: Figure
    waiting: Figure


@dataclass(frozen=True)
class ReportView:
    rows: tuple[RowView, ...]  # new to old
    summary: SummaryView


def rate_text(rate_bp: int) -> str:
    """'1,9%' for 190 basis points."""
    return f"{format(rate_bp_to_pct(rate_bp), 'f').replace('.', ',')}%"


def group_results(results: Sequence[DayResult]) -> list[list[DayResult]]:
    """Days closed by one credit form one group; groups in order of their first day."""
    groups: list[list[DayResult]] = []
    for result in results:
        if groups and groups[-1][0].group_days == result.group_days:
            groups[-1].append(result)
        else:
            groups.append([result])
    return groups


def _member(result: DayResult, rate_bp: int) -> MemberView:
    day = format_date_short(result.sale_date)
    commission = result.expected_commission
    return MemberView(
        day=result.sale_date,
        card_payments=Figure(
            result.card_total,
            "rub",
            (FigureItem(f"Оплаты картой за {day}", result.card_total),),
            SOURCE_CARD,
            f"Оплаты картой из Ветменеджера за {day}.",
        ),
        commission=Figure(
            commission,
            "rub",
            (FigureItem(f"Комиссия по тарифу {rate_text(rate_bp)}", commission),),
            SOURCE_CARD,
            f"Ожидаемая комиссия банка по тарифу {rate_text(rate_bp)} (настройка клиники).",
        ),
        expected=Figure(
            result.expected_credit,
            "rub",
            (FigureItem("Оплаты", result.card_total), FigureItem("Комиссия", -commission)),
            SOURCE_CARD,
            f"Оплаты за вычетом комиссии: столько должно прийти от банка за {day}.",
        ),
    )


def _row(group: Sequence[DayResult], rate_bp: int, credit_text: Mapping[str, str]) -> RowView:
    first, last = group[0], group[-1]
    members = tuple(_member(r, rate_bp) for r in group)
    label = format_range_short(first.sale_date, last.sale_date)
    gross = sum(r.card_total for r in group)
    commission = sum(r.expected_commission for r in group)
    expected = sum(r.expected_credit for r in group)
    expected_by = max(r.expected_by for r in group)
    card = Figure(
        gross,
        "rub",
        tuple(FigureItem(format_date_short(r.sale_date), r.card_total) for r in group),
        SOURCE_CARD,
        f"Оплаты картой из Ветменеджера за {label}.",
    )
    fee = Figure(
        commission,
        "rub",
        (FigureItem(f"Комиссия по тарифу {rate_text(rate_bp)}", commission),),
        SOURCE_CARD,
        f"Ожидаемая комиссия банка по тарифу {rate_text(rate_bp)} (настройка клиники).",
    )
    net = Figure(
        expected,
        "rub",
        (FigureItem("Оплаты", gross), FigureItem("Комиссия", -commission)),
        SOURCE_CARD,
        f"Зачисление ожидаем до {format_day_month(expected_by)}.",
    )
    credited, discrepancy = _credit_figures(first, expected, label, credit_text)
    return RowView(
        first.sale_date, last.sale_date, card, fee, net, credited, discrepancy, first.status,
        expected_by, members, first.credit_id,
    )  # fmt: skip


def _credit_figures(
    first: DayResult, expected: int, label: str, credit_text: Mapping[str, str]
) -> tuple[Figure | None, Figure | None]:
    if first.credit_amount is None or first.diff is None:
        return None, None
    if first.credit_id is None:
        line = FigureItem("Зачислений нет", 0)
        note = f"За {label} банк ничего не зачислил, хотя срок прошёл и выписка его покрывает."
    else:
        when = format_date_short(first.credit_date) if first.credit_date else ""
        line = FigureItem(
            f"{when} · {credit_text.get(first.credit_id, 'зачисление банка')}", first.credit_amount
        )
        note = f"Зачисление банка за {label}: {when}."
    credited = Figure(first.credit_amount, "rub", (line,), SOURCE_BANK, note)
    discrepancy = Figure(
        first.diff,
        "rub",
        (FigureItem("Зачислено", first.credit_amount), FigureItem("Ожидали", -expected)),
        SOURCE_BOTH,
        "Зачислено минус ожидаемое: отрицательное число значит, что банк зачислил меньше.",
    )
    return credited, discrepancy


def _none_item(text: str) -> tuple[FigureItem, ...]:
    return (FigureItem(text, 0),)


def _summary(rows: Sequence[RowView], rate_bp: int) -> SummaryView:
    def labelled(figure_of: str) -> tuple[FigureItem, ...]:
        items: list[FigureItem] = []
        for row in rows:
            figure: Figure | None = getattr(row, figure_of)
            if figure is not None:
                items.append(
                    FigureItem(format_range_short(row.date_from, row.date_to), int(figure.value))
                )
        return tuple(items)

    gross = sum(int(r.card_payments.value) for r in rows)
    commission = sum(int(r.commission.value) for r in rows)
    credited_rows = [r for r in rows if r.credited is not None and r.discrepancy is not None]
    credited = sum(int(r.credited.value) for r in credited_rows if r.credited)
    expected_known = sum(int(r.expected.value) for r in credited_rows)
    waiting_rows = [r for r in rows if r.status == WAITING]
    waiting = sum(int(r.expected.value) for r in waiting_rows)
    return SummaryView(
        card_payments=Figure(
            gross,
            "rub",
            labelled("card_payments") or _none_item("Оплат картой нет"),
            SOURCE_CARD,
            "Оплаты картой из Ветменеджера за месяц.",
        ),  # fmt: skip
        commission=Figure(
            commission,
            "rub",
            (FigureItem(f"Комиссия по тарифу {rate_text(rate_bp)}", commission),),
            SOURCE_CARD,
            f"Ожидаемая комиссия банка по тарифу {rate_text(rate_bp)} (настройка клиники).",
        ),
        credited=Figure(
            credited,
            "rub",
            tuple(
                FigureItem(format_range_short(r.date_from, r.date_to), int(r.credited.value))
                for r in credited_rows
                if r.credited
            )
            or _none_item("Зачислений пока нет"),
            SOURCE_BANK,
            "Зачисления банка по карточным оплатам месяца (из выписок).",
        ),
        discrepancy=Figure(
            credited - expected_known,
            "rub",
            (
                FigureItem("Зачислено", credited),
                FigureItem("Ожидали к зачислению", -expected_known),
            ),
            SOURCE_BOTH,
            "Зачислено минус ожидаемое по дням, где зачисление уже известно.",
        ),
        waiting=Figure(
            waiting,
            "rub",
            tuple(
                FigureItem(format_range_short(r.date_from, r.date_to), int(r.expected.value))
                for r in waiting_rows
            )
            or _none_item("Нет дней в ожидании"),
            SOURCE_CARD,
            "Ожидаемые зачисления за дни, срок которых ещё не наступил.",
        ),
    )


def build_report(
    results: Sequence[DayResult],
    month: str,
    rate_bp: int,
    credit_text: Mapping[str, str],
) -> ReportView:
    """Rows whose first day lies in `month` (YYYY-MM), newest first, and the month totals."""
    rows = [
        _row(group, rate_bp, credit_text)
        for group in group_results(results)
        if group[0].sale_date.strftime("%Y-%m") == month
    ]
    rows.sort(key=lambda r: r.date_from, reverse=True)
    return ReportView(rows=tuple(rows), summary=_summary(rows, rate_bp))
