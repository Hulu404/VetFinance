"""Alerts of the payment calendar (functions 21 and 43): one alert per run of red days, with a suggestion to move one
payment inside the deferral the counterparty allows. Texts are templates filled from the numbers of the engine (no
model in the MVP); `why` has the structure a model can later fill. Rules: tests/golden/set05/README.md, rules 16-21, 26.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from engine.calendar_model import (
    STATUS_BELOW_ZERO,
    NumDay,
    Payment,
    episodes,
    moved,
)
from engine.dashboard_advice import Why
from engine.figure import Figure, FigureItem
from engine.money import format_rub
from engine.obligations import is_workday
from engine.ru import format_day_month, plural

Day = date  # annotations after a field named `date`
MAX_ALERTS = 3
ICON = "\U0001f4c5"
SEVERITY_ALERT = "alert"
SEVERITY_WARNING = "warning"
NO_MOVE_SENTENCE = (
    "Перенос одного платежа разрыв не закрывает. "
    "Если поставщик согласен подождать, укажите отсрочку у его платежа."
)
SOURCES = ("Платёжный календарь", "Поступления за 12 недель", "Отсрочка платежей поставщикам")


@dataclass(frozen=True)
class MoveSuggestion:
    id: str
    payment_id: str
    payment_name: str
    amount: Figure
    from_date: date
    to_date: date
    delay_days: int
    closes_gap: bool
    lowest_after: Figure
    text: str


@dataclass(frozen=True)
class CalendarAlert:
    id: str
    date: date
    date_to: Day
    severity: str
    icon: str
    title: str
    text: str
    shortfall: Figure
    suggestion: MoveSuggestion | None
    why: Why


@dataclass(frozen=True)
class _Candidate:
    payment: Payment
    to: date
    shift: int
    closes: bool
    run_min_after: int
    after: list[NumDay]


def _figure(value: int, items: Sequence[tuple[str, int]], note: str) -> Figure:
    return Figure(
        value=value,
        unit="rub",
        breakdown=tuple(FigureItem(label, v) for label, v in items),
        source=("calc",),
        note=note,
    )


def _candidates(
    days: Sequence[NumDay],
    run: tuple[int, int],
    payments: Sequence[Payment],
    rebuild: Callable[[Sequence[Payment]], list[NumDay]],
    window_end: date,
) -> list[_Candidate]:
    first, last = run
    run_dates = {days[i].date for i in range(first, last + 1)}
    red_before = {d.date for d in days if d.red}
    found: list[_Candidate] = []
    for p in payments:
        if p.max_deferral_days <= 0 or p.date > days[last].date:
            continue
        for k in range(1, p.max_deferral_days + 1):
            to = p.date + timedelta(days=k)
            if not is_workday(to) or to > window_end:
                continue
            after = rebuild(moved(payments, p, to))
            in_run = [d for d in after if d.date in run_dates]
            new_red = [d for d in after if d.red and d.date not in red_before]
            closes = all(not d.red for d in in_run) and not new_red
            if not closes and new_red:
                continue
            found.append(_Candidate(p, to, k, closes, min(d.closing for d in in_run), after))
    return found


def _order(c: _Candidate) -> tuple[int, int, date, str, str]:
    return (c.shift, c.payment.amount, c.payment.date, c.payment.name, c.payment.id)


def _best(cands: Sequence[_Candidate], base_min: int) -> _Candidate | None:
    closing = sorted((c for c in cands if c.closes), key=_order)
    if closing:
        return closing[0]
    better = [c for c in cands if c.run_min_after > base_min]
    if not better:
        return None
    return sorted(better, key=lambda c: (-c.run_min_after, *_order(c)))[0]


def _suggestion(c: _Candidate) -> MoveSuggestion:
    p = c.payment
    amount = format_rub(p.amount)
    frm, to = format_day_month(p.date), format_day_month(c.to)
    if c.closes:
        text = f"Перенесите платёж {p.name} на {amount} с {frm} на {to}: разрыва не будет."
    else:
        text = f"Перенос платежа {p.name} на {amount} с {frm} на {to} уменьшит разрыв, но не закроет его."
    low = min(c.after, key=lambda d: (d.closing, d.date))
    return MoveSuggestion(
        id=f"mv_{p.id}_{c.to:%Y%m%d}",
        payment_id=p.id,
        payment_name=p.name,
        amount=_figure(p.amount, [(p.name, p.amount)], "Платёж, который предлагаем перенести."),
        from_date=p.date,
        to_date=c.to,
        delay_days=c.shift,
        closes_gap=c.closes,
        lowest_after=_figure(
            low.closing,
            [(f"Остаток на вечер {format_day_month(low.date)}", low.closing)],
            "Самый низкий остаток окна, если перенести платёж.",
        ),
        text=text,
    )


def _worst_point(run_days: Sequence[NumDay]) -> tuple[int, NumDay, int, str]:
    """(balance, day, index of the payment or -1 for the evening, ...) of the lowest point of a run."""
    best: tuple[int, NumDay, int] | None = None
    for d in run_days:
        points = [(after, i) for i, (_, after) in enumerate(d.payments)] + [(d.closing, -1)]
        for value, idx in points:
            if best is None or value < best[0]:
                best = (value, d, idx)
    assert best is not None  # noqa: S101 (a run has days)
    return best[0], best[1], best[2], ""


def _shortfall_alert(run_days: Sequence[NumDay]) -> tuple[Figure, str]:
    value, day, idx, _ = _worst_point(run_days)
    label = format_day_month(day.date)
    paid = (
        sum(p.amount for p, _ in day.payments[: idx + 1])
        if idx >= 0
        else sum(p.amount for p, _ in day.payments)
    )
    items = [(f"К выплате {label}", paid), ("Будет на утро", -day.opening)]
    if idx < 0:
        items.append(("Выручка, прогноз", -day.income))
    return (
        _figure(-value, items, "Сколько не хватает до нуля в самой низкой точке."),
        f"{label}: на утро будет {format_rub(day.opening)}, к выплате {format_rub(paid)}.",
    )


def _why(
    run_days: Sequence[NumDay], severity: str, safe: int, shortfall: int, sug: MoveSuggestion | None
) -> Why:
    first = run_days[0]
    paid = sum(p.amount for p, _ in first.payments)
    steps = [
        f"{format_day_month(first.date)}: на утро {format_rub(first.opening)}, "
        + (f"к выплате {format_rub(paid)}." if paid else "платежей нет."),
        f"Выручку дня, {format_rub(first.income)}, считаем после платежей: "
        f"к вечеру останется {format_rub(first.closing)}.",
        f"Безопасный запас {format_rub(safe)}: не хватает {format_rub(shortfall)}."
        if severity == SEVERITY_WARNING
        else f"Денег не хватает на платежи: {format_rub(shortfall)}.",
    ]
    if len(run_days) > 1:
        n = len(run_days)
        steps.append(
            f"Разрыв длится {n} {plural(n, 'день', 'дня', 'дней')}: "
            f"с {format_day_month(run_days[0].date)} по {format_day_month(run_days[-1].date)}."
        )
    if sug is not None:
        steps.append(
            f"Если перенести платёж {sug.payment_name} на {format_day_month(sug.to_date)}, "
            f"самый низкий остаток окна будет {format_rub(int(sug.lowest_after.value))}."
        )
    else:
        steps.append("Перенос одного платежа разрыв не закрывает.")
    summary = (
        "К этому дню платежи уходят быстрее, чем приходит выручка."
        if severity == SEVERITY_WARNING
        else "Денег на счетах не хватает на запланированные платежи."
    )
    return Why(summary, tuple(steps[:5]), SOURCES)


def build_alerts(
    days: Sequence[NumDay],
    payments: Sequence[Payment],
    safe_balance: int,
    rebuild: Callable[[Sequence[Payment]], list[NumDay]],
    window_end: date,
) -> tuple[CalendarAlert, ...]:
    alerts: list[CalendarAlert] = []
    for first, last in episodes(days)[:MAX_ALERTS]:
        run_days = days[first : last + 1]
        low = min(run_days, key=lambda d: (d.closing, d.date))
        cands = _candidates(days, (first, last), payments, rebuild, window_end)
        best = _best(cands, min(d.closing for d in run_days))
        sug = _suggestion(best) if best else None
        day_text = format_day_month(run_days[0].date)
        if any(d.status == STATUS_BELOW_ZERO for d in run_days):
            severity = SEVERITY_ALERT
            shortfall, text = _shortfall_alert(
                [d for d in run_days if d.status == STATUS_BELOW_ZERO]
            )
            title = f"{day_text}: не хватит {format_rub(int(shortfall.value))} на платежи"
        else:
            severity = SEVERITY_WARNING
            value = safe_balance - low.closing
            shortfall = _figure(
                value,
                [
                    ("Безопасный запас", safe_balance),
                    (f"Остаток на вечер {format_day_month(low.date)}", -low.closing),
                ],
                "Сколько не хватает до безопасного запаса в самой низкой точке.",
            )
            title = f"{day_text}: остаток ниже безопасного запаса на {format_rub(value)}"
            text = (
                f"Вечером {format_day_month(low.date)} останется {format_rub(low.closing)} "
                f"при запасе {format_rub(safe_balance)}."
            )
        if sug is None:
            text += " " + NO_MOVE_SENTENCE
        alerts.append(
            CalendarAlert(
                id=f"gap_{run_days[0].date:%Y%m%d}",
                date=run_days[0].date,
                date_to=run_days[-1].date,
                severity=severity,
                icon=ICON,
                title=title,
                text=text,
                shortfall=shortfall,
                suggestion=sug,
                why=_why(run_days, severity, safe_balance, int(shortfall.value), sug),
            )
        )
    return tuple(alerts)
