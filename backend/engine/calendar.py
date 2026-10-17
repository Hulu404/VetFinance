"""Payment calendar for 22 days (functions 21, 22, 43): balance on every day, regular payments found in the bank
history, forecast of income by weekday, obligations, manual payments, alerts with a suggestion to move a payment.

Pure functions: a snapshot of the data and `as_of` give the same numbers every time. Rules and their numbers:
tests/golden/set05/README.md (rules 1-26); the decisions of the owner of 2026-10-16 in docs/handoff.md.
Money in kopecks, rounding only through engine/money.py.
"""

import hashlib
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta

from engine.balance import AccountInput, TransactionInput, compute_balance
from engine.calendar_alerts import CalendarAlert, build_alerts
from engine.calendar_model import (
    SOURCE_MANUAL,
    SOURCE_OBLIGATION,
    SOURCE_RECURRING,
    STATUS_OK,
    WEEKDAYS,
    WINDOW_DAYS,
    NumDay,
    Payment,
    build_days,
)
from engine.figure import Figure, FigureItem
from engine.money import div_round, format_rub
from engine.obligations import (
    add_months,
    month_first,
    nominal_date,
    payments_between,
    shift_off_day,
)
from engine.planning_inputs import (
    CounterpartyTermsInput,
    ObligationInput,
    PaymentMoveInput,
    PlannedPaymentInput,
    counterparty_key,
)
from engine.reports_inputs import (
    TYPE_FIXED,
    TYPE_INCOME,
    TYPE_OBLIGATION,
    TYPE_TAX,
    TYPE_VARIABLE,
    CategoryInput,
)
from engine.ru import MONTHS_NOMINATIVE, format_day_month, format_days_range, month_genitive

PROFILE_WEEKS = 12
PROFILE_DAYS = PROFILE_WEEKS * 7
ANALYSIS_MONTHS = 6
REGULAR_MONTHS = 3
AMOUNT_TOLERANCE_PCT = 25
DETECTED_TYPES = frozenset({TYPE_VARIABLE, TYPE_FIXED, TYPE_TAX, None})
MIN_HISTORY_DAYS = (
    PROFILE_DAYS + 1
)  # `history_days` counts the day of as_of, the profile stops the day before
OBLIGATION_LOOKBACK_DAYS = 90
SHIFT_FORWARD = "next"
SHIFT_BACK = "prev"
WEEKDAYS_DATIVE = (
    "понедельникам", "вторникам", "средам", "четвергам", "пятницам", "субботам", "воскресеньям",
)  # fmt: skip
STATUS_STATEMENT_DUPLICATE = "duplicate"
SOURCE_BANK = "bank"


@dataclass(frozen=True)
class RecurringSlot:
    slot: int
    day: int
    amount: int
    last_amounts: tuple[int, ...]
    days_seen: tuple[int, ...]


@dataclass(frozen=True)
class RecurringSeries:
    key: str
    counterparty_key: str
    inn: str | None
    name: str
    category: str | None
    type: str | None
    slots: tuple[RecurringSlot, ...]
    shift: str
    max_deferral_days: int
    last_months: tuple[date, ...] = ()


@dataclass(frozen=True)
class ProfileRow:
    weekday: int  # 0 = Monday
    sum: int
    days: int
    average: int


@dataclass(frozen=True)
class CalendarPayment:
    id: str
    name: str
    category: str | None
    counterparty_key: str | None
    counterparty_inn: str | None
    counterparty_name: str | None
    amount: Figure
    source: str
    balance_after: Figure
    max_deferral_days: int
    moved_from: date | None


@dataclass(frozen=True)
class CalendarDay:
    date: date
    weekday: str
    opening: Figure
    income_forecast: Figure
    payments: tuple[CalendarPayment, ...]
    closing: Figure
    status: str
    below_safe: bool
    note: str


@dataclass(frozen=True)
class Lowest:
    date: date
    balance: Figure
    status: str


@dataclass(frozen=True)
class CalendarSummary:
    income: Figure
    expense: Figure
    payments_count: int
    lowest: Lowest


@dataclass(frozen=True)
class CalendarResult:
    as_of: date
    window_from: date
    window_to: date
    status: str  # ok | partial | empty
    partial_reasons: tuple[str, ...]
    history_days: int
    start_balance: Figure
    safe_balance: Figure
    safe_balance_set: bool
    summary: CalendarSummary
    alerts: tuple[CalendarAlert, ...]
    days: tuple[CalendarDay, ...]


# ------------------------------------------------------------------ history helpers
def _types(categories: Sequence[CategoryInput]) -> dict[str, str]:
    return {c.name: c.type for c in categories}


def _history_start(
    transactions: Sequence[TransactionInput], history_from: date | None
) -> date | None:
    if history_from is not None:
        return history_from
    return min((t.date for t in transactions), default=None)


def _median_of_three(values: Sequence[int]) -> int:
    return sorted(values)[len(values) // 2]


def _identity(t: TransactionInput) -> str:
    return t.counterparty_inn or t.counterparty_name


# ------------------------------------------------------------------ regular payments (function 22)
def detect_recurring(
    transactions: Sequence[TransactionInput],
    categories: Sequence[CategoryInput],
    as_of: date,
    counterparties: Sequence[CounterpartyTermsInput] = (),
    history_from: date | None = None,
) -> list[RecurringSeries]:
    """Series of payments made in each of the 3 last full months with the same number of payments per month and an
    amount that stays within 25% of its median (rules 6-10)."""
    types = _types(categories)
    first = _history_start(transactions, history_from)
    if first is None:
        return []
    this_month = month_first(as_of)
    months = [add_months(this_month, -n) for n in range(ANALYSIS_MONTHS, 0, -1)]
    months = [m for m in months if m >= month_first(first)]
    last3 = months[-REGULAR_MONTHS:]
    if len(last3) < REGULAR_MONTHS:
        return []
    terms = {c.inn: c.max_deferral_days for c in counterparties}
    groups: dict[tuple[str, str | None], list[TransactionInput]] = defaultdict(list)
    for t in transactions:
        if t.kind != "out" or t.status == STATUS_STATEMENT_DUPLICATE:
            continue
        if types.get(t.category or "") not in DETECTED_TYPES:
            continue
        if month_first(t.date) in months:
            groups[(_identity(t), t.category)].append(t)
    found: list[RecurringSeries] = []
    for key in sorted(groups, key=lambda k: (k[0], k[1] or "")):
        series = _series(key, groups[key], months, last3, types, terms)
        if series is not None:
            found.append(series)
    return found


def _series(
    key: tuple[str, str | None],
    ops: list[TransactionInput],
    months: list[date],
    last3: list[date],
    types: dict[str, str],
    terms: dict[str, int],
) -> RecurringSeries | None:
    ops = sorted(ops, key=lambda t: (t.date, -t.amount, t.counterparty_name))
    per_month: dict[date, list[TransactionInput]] = defaultdict(list)
    for t in ops:
        per_month[month_first(t.date)].append(t)
    counts = [len(per_month[m]) for m in last3]
    if min(counts) == 0 or len(set(counts)) != 1:
        return None
    slots: list[RecurringSlot] = []
    for s in range(counts[0]):
        history = [per_month[m][s] for m in months if len(per_month[m]) == counts[0]]
        last_amounts = tuple(-per_month[m][s].amount for m in last3)
        median = _median_of_three(last_amounts)
        if any(abs(a - median) * 100 > AMOUNT_TOLERANCE_PCT * median for a in last_amounts):
            return None
        seen = Counter(t.date.day for t in history)
        top = max(seen.values())
        day = max(
            d for d, c in seen.items() if c == top
        )  # a tie takes the later day: weekends shift earlier
        slots.append(
            RecurringSlot(s + 1, day, median, last_amounts, tuple(t.date.day for t in history))
        )
    latest = ops[-1]
    category = key[1]
    kind = types.get(category) if category else None
    cp_key = counterparty_key(latest.counterparty_inn, latest.counterparty_name)
    return RecurringSeries(
        key=f"{key[0]}|{category or ''}",
        counterparty_key=cp_key,
        inn=latest.counterparty_inn or None,
        name=latest.counterparty_name,
        category=category,
        type=kind,
        slots=tuple(slots),
        shift=SHIFT_FORWARD if kind == TYPE_TAX else SHIFT_BACK,
        max_deferral_days=terms.get(cp_key, 0),
        last_months=tuple(last3),
    )


def _forecast_recurring(
    series: Sequence[RecurringSeries],
    transactions: Sequence[TransactionInput],
    as_of: date,
    window_end: date,
) -> list[Payment]:
    out: list[Payment] = []
    this_month = month_first(as_of)
    month = this_month
    months = []
    while month <= window_end:
        months.append(month)
        month = add_months(month, 1)
    for ser in series:
        digest = hashlib.sha256((ser.category or "").encode("utf-8")).hexdigest()[:6]
        paid_now = sum(
            1
            for t in transactions
            if t.kind == "out"
            and t.status != STATUS_STATEMENT_DUPLICATE
            and (t.counterparty_inn or t.counterparty_name) == (ser.inn or ser.name)
            and t.category == ser.category
            and month_first(t.date) == this_month
            and t.date <= as_of
        )
        for m in months:
            for slot in ser.slots:
                if m == this_month and slot.slot <= paid_now:
                    continue  # already paid this month
                nominal = nominal_date(m, slot.day)
                day = shift_off_day(nominal, forward=ser.shift == SHIFT_FORWARD)
                if as_of <= day <= window_end:
                    out.append(
                        Payment(
                            id=f"rec_{ser.counterparty_key}_{digest}_{slot.slot}_{day:%Y%m%d}",
                            date=day,
                            name=ser.name,
                            amount=slot.amount,
                            source=SOURCE_RECURRING,
                            category=ser.category,
                            counterparty_key=ser.counterparty_key,
                            counterparty_inn=ser.inn,
                            counterparty_name=ser.name,
                            max_deferral_days=ser.max_deferral_days,
                            nominal_date=nominal,
                            details=tuple(
                                (MONTHS_NOMINATIVE[m.month - 1].capitalize(), a)
                                for m, a in zip(ser.last_months, slot.last_amounts, strict=True)
                            ),
                        )
                    )
    return out


# ------------------------------------------------------------------ income by weekday
def income_profile(
    transactions: Sequence[TransactionInput],
    categories: Sequence[CategoryInput],
    as_of: date,
    history_from: date | None = None,
) -> list[ProfileRow]:
    """Average income per weekday over the 12 full weeks before `as_of` (rule 5): operations `in` of articles of type
    income, no duplicates; fewer days of history divide by the days that exist."""
    types = _types(categories)
    first = _history_start(transactions, history_from)
    end = as_of - timedelta(days=1)
    start = as_of - timedelta(days=PROFILE_DAYS)
    if first is not None:
        start = max(start, first)
    sums, counts = [0] * 7, [0] * 7
    day = start
    while day <= end:
        counts[day.weekday()] += 1
        day += timedelta(days=1)
    for t in transactions:
        if not start <= t.date <= end or t.kind != "in" or t.status == STATUS_STATEMENT_DUPLICATE:
            continue
        if t.category and types.get(t.category) == TYPE_INCOME:
            sums[t.date.weekday()] += t.amount
    return [
        ProfileRow(i, sums[i], counts[i], div_round(sums[i], counts[i]) if counts[i] else 0)
        for i in range(7)
    ]


# ------------------------------------------------------------------ figures
def _fig(
    value: int,
    items: Sequence[tuple[str, int]],
    source: tuple[str, ...],
    note: str,
    details: Sequence[FigureItem] = (),
) -> Figure:
    return Figure(
        value=value,
        unit="rub",
        breakdown=tuple(FigureItem(label, v) for label, v in items),
        source=source,
        note=note,
        details=tuple(details),
    )


def _week_groups(days: Sequence[NumDay]) -> list[list[NumDay]]:
    groups: list[list[NumDay]] = []
    for d in days:
        if not groups or d.date.weekday() == 0:
            groups.append([])
        groups[-1].append(d)
    return groups


def _by_week(days: Sequence[NumDay], income: bool) -> list[tuple[str, int]]:
    rows = []
    for group in _week_groups(days):
        total = sum(d.income if income else sum(p.amount for p, _ in d.payments) for d in group)
        rows.append((format_days_range(group[0].date, group[-1].date), total))
    return rows


def _day_note(day: NumDay, safe: int) -> str:
    if day.status == STATUS_OK:
        return f"Запас соблюдён: остаток выше {format_rub(safe)}."
    return f"Остаток на вечер ниже безопасного запаса на {format_rub(safe - day.closing)}."


def _calendar_day(
    day: NumDay,
    index: int,
    safe: int,
    start_figure: Figure,
    prev_label: str,
    profile: Sequence[ProfileRow],
    statement_income: int,
) -> CalendarDay:
    prof = profile[day.date.weekday()]
    if index == 0:
        opening = start_figure
    else:
        opening = _fig(
            day.opening, [(prev_label, day.opening)], ("calc",), "Остаток на вечер предыдущего дня."
        )
    items = [(f"Среднее поступление по {WEEKDAYS_DATIVE[day.date.weekday()]}", prof.average)]
    if index == 0 and statement_income:
        items.append(("Уже в выписке за сегодня", -min(statement_income, prof.average)))
    income = _fig(
        day.income,
        items,
        ("calc",),
        f"{format_rub(prof.sum)} ÷ {prof.days} = {format_rub(prof.average)}. "
        "Только поступления со статьёй дохода: возвраты, операции «на проверку», дубли и переводы между счетами не входят.",
        (
            FigureItem("Таких дней за 12 недель", prof.days, "count"),
            FigureItem("Поступило в эти дни", prof.sum),
        ),
    )
    note = _day_note(day, safe)
    payments = tuple(_calendar_payment(p, after, before) for (p, after), before in _befores(day))
    closing = _fig(
        day.closing,
        [("На утро", day.opening)]
        + [(p.name, -p.amount) for p, _ in day.payments]
        + [("Выручка, прогноз", day.income)],
        ("calc",),
        note,
    )
    return CalendarDay(
        date=day.date,
        weekday=WEEKDAYS[day.date.weekday()],
        opening=opening,
        income_forecast=income,
        payments=payments,
        closing=closing,
        status=day.status,
        below_safe=day.red,
        note=note,
    )


def _befores(day: NumDay) -> list[tuple[tuple[Payment, int], int]]:
    out, running = [], day.opening
    for item in day.payments:
        out.append((item, running))
        running = item[1]
    return out


_PAYMENT_NOTES = {
    SOURCE_RECURRING: "Повторяется каждый месяц: найден в выписке банка.",
    SOURCE_OBLIGATION: "Платёж по графику из раздела «Обязательства».",
    SOURCE_MANUAL: "Платёж внесён вручную.",
}


def _payment_note(p: Payment) -> str:
    if p.source != SOURCE_RECURRING or p.nominal_date is None:
        return _PAYMENT_NOTES[p.source]
    note = (
        "Платёж был в каждом из трёх последних месяцев. "
        f"День — самый частый день месяца ({p.nominal_date.day}-е), "
        f"сумма — средняя из трёх (медиана): {format_rub(p.amount)}."
    )
    if p.nominal_date != p.date:
        note += " Выпал на выходной: налоги сдвигаем на понедельник, остальное на пятницу."
    return note


def _calendar_payment(p: Payment, after: int, before: int) -> CalendarPayment:
    source = (SOURCE_BANK,) if p.source == SOURCE_RECURRING else ("manual",)
    return CalendarPayment(
        id=p.id,
        name=p.name,
        category=p.category,
        counterparty_key=p.counterparty_key,
        counterparty_inn=p.counterparty_inn,
        counterparty_name=p.counterparty_name,
        amount=_fig(
            p.amount,
            [(p.name, p.amount)],
            source,
            _payment_note(p),
            [FigureItem(label, value) for label, value in p.details],
        ),
        source=p.source,
        balance_after=_fig(
            after,
            [("До платежа", before), (p.name, -p.amount)],
            ("calc",),
            "Выручку дня считаем после платежей: деньги приходят в течение дня.",
        ),
        max_deferral_days=p.max_deferral_days,
        moved_from=p.moved_from,
    )


# ------------------------------------------------------------------ the calendar
def _apply_moves(payments: list[Payment], moves: Sequence[PaymentMoveInput]) -> list[Payment]:
    result = list(payments)
    for move in moves:
        for i, p in enumerate(result):
            hit = (
                p.id == move.payment_id
                if move.payment_id
                else (p.name, p.source, p.date) == (move.name, move.source, move.from_date)
            )
            if hit:
                result[i] = replace(p, date=move.to_date, moved_from=p.date)
                break
    return result


def _already_in_statement(
    ob: ObligationInput,
    amount: int,
    transactions: Sequence[TransactionInput],
    as_of: date,
    types: dict[str, str],
) -> bool:
    return any(
        t.date == as_of
        and t.kind == "out"
        and -t.amount == amount
        and types.get(t.category or "") == TYPE_OBLIGATION
        for t in transactions
    )


def _all_payments(
    transactions: Sequence[TransactionInput],
    categories: Sequence[CategoryInput],
    obligations: Sequence[ObligationInput],
    planned: Sequence[PlannedPaymentInput],
    counterparties: Sequence[CounterpartyTermsInput],
    as_of: date,
    window_end: date,
    history_from: date | None,
) -> list[Payment]:
    types = _types(categories)
    series = detect_recurring(transactions, categories, as_of, counterparties, history_from)
    payments = _forecast_recurring(series, transactions, as_of, window_end)
    for ob, row in payments_between(obligations, as_of, window_end):
        if row.date == as_of and _already_in_statement(ob, row.payment, transactions, as_of, types):
            continue
        payments.append(
            Payment(
                id=f"obl_{ob.id}_{row.date:%Y%m%d}",
                date=row.date,
                name=ob.name,
                amount=row.payment,
                source=SOURCE_OBLIGATION,
                nominal_date=nominal_date(row.month, ob.payment_day or 1),
                details=(
                    (
                        (f"Проценты за {month_genitive(row.month.month)}", row.interest),
                        ("Основной долг", row.principal),
                    )
                    if ob.kind == "loan"
                    else ()
                ),
            )
        )
    for p in planned:
        if as_of <= p.date <= window_end:
            payments.append(
                Payment(
                    id=p.id,
                    date=p.date,
                    name=p.name,
                    amount=p.amount,
                    source=SOURCE_MANUAL,
                    category=p.category,
                    max_deferral_days=p.max_deferral_days,
                    nominal_date=p.date,
                )
            )
    return sorted(payments, key=lambda p: (p.date, -p.amount, p.name, p.id))


def _short_history(first: date, history_days: int, as_of: date) -> bool:
    """Fewer than 84 days before `as_of` (history_days < 85), or without three full calendar months before the month of `as_of`."""
    first_full = first if first.day == 1 else add_months(month_first(first), 1)
    needed = add_months(month_first(as_of), -REGULAR_MONTHS)
    return history_days < MIN_HISTORY_DAYS or first_full > needed


def _statement_flags(
    transactions: Sequence[TransactionInput],
    categories: Sequence[CategoryInput],
    obligations: Sequence[ObligationInput],
    accounts: Sequence[AccountInput],
    as_of: date,
) -> tuple[str, tuple[str, ...], int]:
    types = _types(categories)
    bank_days = [t.date for t in transactions if t.source == SOURCE_BANK and t.date <= as_of]
    history_days = (as_of - min(bank_days)).days + 1 if bank_days else 0
    if not accounts or not transactions:
        return "empty", (), history_days
    reasons = []
    if bank_days and _short_history(min(bank_days), history_days, as_of):
        reasons.append("short_history")
    lookback = as_of - timedelta(days=OBLIGATION_LOOKBACK_DAYS)
    paid_credit = any(
        t.kind == "out"
        and t.category
        and types.get(t.category) == TYPE_OBLIGATION
        and lookback <= t.date <= as_of
        for t in transactions
    )
    has_loans = any(o.kind in ("loan", "lease") and o.closed_from is None for o in obligations)
    if paid_credit and not has_loans:
        reasons.append("obligations_missing")
    if not bank_days:
        reasons.append("no_bank")
    return ("partial" if reasons else "ok"), tuple(reasons), history_days


def compute_calendar(
    accounts: Sequence[AccountInput],
    transactions: Sequence[TransactionInput],
    categories: Sequence[CategoryInput],
    obligations: Sequence[ObligationInput],
    planned_payments: Sequence[PlannedPaymentInput],
    counterparties: Sequence[CounterpartyTermsInput],
    safe_balance: int,
    as_of: date,
    days: int = WINDOW_DAYS,
    moves: Sequence[PaymentMoveInput] = (),
) -> CalendarResult:
    """The window of `days` days from `as_of` (rule 1): balance on every day, payments, alerts."""
    window_end = as_of + timedelta(days=days - 1)
    open_accounts = [a for a in accounts if a.opening_date <= as_of]
    history_from = min((a.opening_date for a in accounts), default=None)
    balance = compute_balance(open_accounts, transactions, as_of)
    start = _start_figure(balance.total, open_accounts, as_of)
    profile = income_profile(transactions, categories, as_of, history_from)
    types = _types(categories)
    statement_income = sum(
        t.amount
        for t in transactions
        if t.date == as_of
        and t.kind == "in"
        and t.status != STATUS_STATEMENT_DUPLICATE
        and types.get(t.category or "") == TYPE_INCOME
    )

    def income_for(day: date) -> int:
        average = profile[day.weekday()].average
        return max(0, average - statement_income) if day == as_of else average

    payments = _apply_moves(
        _all_payments(
            transactions,
            categories,
            obligations,
            planned_payments,
            counterparties,
            as_of,
            window_end,
            history_from,
        ),
        moves,
    )

    def rebuild(ps: Sequence[Payment]) -> list[NumDay]:
        return build_days(as_of, balance.total.value, income_for, ps, safe_balance, days)  # type: ignore[arg-type]

    num_days = rebuild(payments)
    alerts = build_alerts(num_days, payments, safe_balance, rebuild, window_end)
    rows: list[CalendarDay] = []
    prev_label = ""
    for i, d in enumerate(num_days):
        rows.append(_calendar_day(d, i, safe_balance, start, prev_label, profile, statement_income))
        prev_label = f"Остаток на вечер {format_day_month(d.date)}"
    low = min(rows, key=lambda r: (r.closing.value, r.date))
    status, reasons, history_days = _statement_flags(
        transactions, categories, obligations, accounts, as_of
    )
    count = sum(len(d.payments) for d in rows)
    summary = CalendarSummary(
        income=_fig(
            sum(d.income for d in num_days),
            _by_week(num_days, True),
            ("calc",),
            "Прогноз выручки: среднее поступлений по дню недели за последние 12 недель.",
        ),
        expense=_fig(
            sum(p.amount for p in payments),
            _by_week(num_days, False),
            (SOURCE_BANK, "manual"),
            f"{count} платежей: аренда, зарплата, поставщики, налоги, кредит и лизинг.",
            _expense_details(payments),
        ),
        payments_count=count,
        lowest=Lowest(low.date, low.closing, low.status),
    )
    return CalendarResult(
        as_of=as_of,
        window_from=as_of,
        window_to=window_end,
        status=status,
        partial_reasons=reasons,
        history_days=history_days,
        start_balance=start,
        safe_balance=_fig(
            safe_balance,
            [("Задан в настройках", safe_balance)],
            ("manual",),
            "Если остаток на вечер ниже этой суммы, день отмечается красным и подписью «ниже запаса».",
        ),
        safe_balance_set=safe_balance > 0,
        summary=summary,
        alerts=alerts,
        days=tuple(rows),
    )


def _start_figure(total: Figure, accounts: Sequence[AccountInput], as_of: date) -> Figure:
    """Balance on the morning of `as_of` by account, bank accounts first (the tooltip of the first day)."""
    rank = {a.name: (a.kind != "bank", a.name) for a in accounts}
    items = sorted(total.breakdown, key=lambda i: rank.get(i.label, (True, i.label)))
    return replace(
        total,
        breakdown=tuple(items),
        note=(
            f"Остаток на утро {format_day_month(as_of)}: банк по вчерашний день и касса. "
            "Так же считается остаток на Рабочем столе."
        ),
    )


def _expense_details(payments: Sequence[Payment]) -> list[FigureItem]:
    totals = {SOURCE_RECURRING: 0, SOURCE_OBLIGATION: 0, SOURCE_MANUAL: 0}
    for p in payments:
        totals[p.source] += p.amount
    return [
        FigureItem("Регулярные платежи", totals[SOURCE_RECURRING]),
        FigureItem("Обязательства", totals[SOURCE_OBLIGATION]),
        FigureItem("Внесено вручную", totals[SOURCE_MANUAL]),
    ]
