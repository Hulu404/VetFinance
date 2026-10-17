"""Obligations (function 23): loans, leases and equipment. Payments, accruals and the summary come from the terms.

Rules (tests/golden/set05/README.md, rules 22-24): a loan is an annuity, the interest of a month is
`balance on the 1st x rate / 12`, the last payment is the balance plus its interest; a lease goes to the P&L in full,
the leased item is not amortised; equipment is amortised in a straight line from the month after the start of
service, `years x 12` months, the last month takes what is left. A payment on a weekend moves to the previous
working day. Accruals cover the whole calendar month. Pure functions, money in kopecks, rounding in engine/money.py.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from engine.figure import Figure, FigureItem
from engine.money import div_round, format_rub, pct_one_decimal
from engine.planning_inputs import KIND_EQUIPMENT, KIND_LEASE, KIND_LOAN, ObligationInput
from engine.reports_inputs import ObligationChargeInput
from engine.ru import month_genitive, month_name

MONTHS_IN_YEAR = 12
RATE_DIVISOR = 10_000 * MONTHS_IN_YEAR  # annual rate in basis points -> rate of a month
CHARGE_LOAN = "loan_interest"
CHARGE_LEASE = "lease"
CHARGE_AMORTIZATION = "amortization"
STATUS_ACTIVE = "active"
STATUS_PAID = "paid"
STATUS_CLOSED = "closed"
SATURDAY = 5


@dataclass(frozen=True)
class PaymentRow:
    month: date  # the 1st of the payment month
    date: date  # the day the payment is made (weekend moved back)
    payment: int
    interest: int  # loans only, else 0
    principal: int  # loans only, else 0
    balance_before: int  # debt before the payment (loans) or what is left to pay (leases)
    balance_after: int


@dataclass(frozen=True)
class LoanResult:
    id: str
    kind: str
    name: str
    lender: str | None
    principal: Figure
    remaining: Figure
    paid_pct: Figure
    payment: Figure
    rate_pct: float | None
    payment_day: int
    next_payment_date: date | None
    until: str  # YYYY-MM of the last payment
    status: str
    closed_from: str | None


@dataclass(frozen=True)
class EquipmentResult:
    id: str
    name: str
    cost: Figure
    life_years: int
    in_service_from: date
    amortization_from: str
    amortization_to: str
    monthly: Figure
    status: str
    closed_from: str | None
    this_month: int  # accrual of the month of `as_of`


@dataclass(frozen=True)
class ObligationsResult:
    as_of: date
    month: str
    debt_total: Figure
    monthly_payment: Figure
    amortization_month: Figure
    charges_month: Figure
    loans: tuple[LoanResult, ...]
    equipment: tuple[EquipmentResult, ...]


# ------------------------------------------------------------------ calendar helpers
def month_first(day: date) -> date:
    return day.replace(day=1)


def add_months(first: date, count: int) -> date:
    index = first.year * MONTHS_IN_YEAR + first.month - 1 + count
    return date(index // MONTHS_IN_YEAR, index % MONTHS_IN_YEAR + 1, 1)


def nominal_date(first: date, day: int) -> date:
    last = add_months(first, 1) - timedelta(days=1)
    return first.replace(day=min(day, last.day))


def is_workday(day: date) -> bool:
    return day.weekday() < SATURDAY


def shift_off_day(day: date, forward: bool = False) -> date:
    step = timedelta(days=1 if forward else -1)
    while not is_workday(day):
        day += step
    return day


def month_key(first: date) -> str:
    return f"{first.year}-{first.month:02d}"


# ------------------------------------------------------------------ schedules
def loan_schedule(ob: ObligationInput) -> list[PaymentRow]:
    if (
        ob.first_payment_date is None
        or ob.payments_total is None
        or ob.payment is None
        or ob.payment_day is None
    ):
        return []
    balance = ob.start_balance if ob.start_balance is not None else (ob.principal or 0)
    rate_bp = ob.annual_rate_bp or 0
    first = month_first(ob.first_payment_date)
    rows: list[PaymentRow] = []
    for n in range(ob.payments_total):
        month = add_months(first, n)
        interest = div_round(balance * rate_bp, RATE_DIVISOR)
        last = n == ob.payments_total - 1 or balance + interest <= ob.payment
        payment = balance + interest if last else ob.payment
        principal = payment - interest
        day = shift_off_day(nominal_date(month, ob.payment_day))
        rows.append(
            PaymentRow(month, day, payment, interest, principal, balance, balance - principal)
        )
        balance -= principal
        if balance == 0:
            break
    return rows


def lease_schedule(ob: ObligationInput) -> list[PaymentRow]:
    if (
        ob.first_payment_date is None
        or ob.payments_total is None
        or ob.payment is None
        or ob.payment_day is None
    ):
        return []
    left = ob.start_balance if ob.start_balance is not None else ob.payment * ob.payments_total
    first = month_first(ob.first_payment_date)
    rows: list[PaymentRow] = []
    for n in range(ob.payments_total):
        month = add_months(first, n)
        amount = left if n == ob.payments_total - 1 else min(ob.payment, left)
        day = shift_off_day(nominal_date(month, ob.payment_day))
        rows.append(PaymentRow(month, day, amount, 0, 0, left, left - amount))
        left -= amount
    return rows


def amortization_rows(ob: ObligationInput) -> list[tuple[date, int]]:
    """(first day of the month, accrual) for each month of the life of the equipment."""
    if ob.cost is None or ob.life_years is None or ob.in_service_date is None:
        return []
    months = ob.life_years * MONTHS_IN_YEAR
    monthly = div_round(ob.cost, months)
    start = add_months(month_first(ob.in_service_date), 1)
    return [
        (add_months(start, i), monthly if i < months - 1 else ob.cost - monthly * (months - 1))
        for i in range(months)
    ]


def schedule(ob: ObligationInput) -> list[PaymentRow]:
    if ob.kind == KIND_LOAN:
        return loan_schedule(ob)
    if ob.kind == KIND_LEASE:
        return lease_schedule(ob)
    return []


def _active_in(ob: ObligationInput, first: date) -> bool:
    """Is the month `first` inside the life of the obligation record (effective and not closed)?"""
    if ob.effective_from is not None and first < ob.effective_from:
        return False
    return ob.closed_from is None or first < ob.closed_from


def payments_between(
    obligations: Iterable[ObligationInput], first: date, last: date
) -> list[tuple[ObligationInput, PaymentRow]]:
    """Loan and lease payments made on days `first..last` (closed obligations pay nothing)."""
    found = []
    for ob in obligations:
        if ob.kind not in (KIND_LOAN, KIND_LEASE):
            continue
        for row in schedule(ob):
            if first <= row.date <= last and (ob.closed_from is None or row.month < ob.closed_from):
                found.append((ob, row))
    found.sort(key=lambda pair: (pair[1].date, pair[0].name, pair[0].id))
    return found


# ------------------------------------------------------------------ accruals
def compute_obligation_charges(
    obligations: Sequence[ObligationInput], month: date
) -> list[ObligationChargeInput]:
    """Accruals of the whole calendar month of `month`: loan interest, lease payment, amortization."""
    first = month_first(month)
    key = month_key(first)
    charges: list[ObligationChargeInput] = []
    for ob in obligations:
        if not _active_in(ob, first):
            continue
        if ob.kind in (KIND_LOAN, KIND_LEASE):
            kind = CHARGE_LOAN if ob.kind == KIND_LOAN else CHARGE_LEASE
            for row in schedule(ob):
                if row.month == first:
                    amount = row.interest if ob.kind == KIND_LOAN else row.payment
                    charges.append(ObligationChargeInput(key, ob.id, ob.name, kind, amount))
        else:
            for start, amount in amortization_rows(ob):
                if start == first:
                    charges.append(
                        ObligationChargeInput(key, ob.id, ob.name, CHARGE_AMORTIZATION, amount)
                    )
    return sorted(charges, key=lambda c: (c.obligation_id, c.kind))


# ------------------------------------------------------------------ summary
def _fig(
    value: int | Decimal,
    items: Sequence[tuple[str, int]],
    source: tuple[str, ...],
    note: str,
    *,
    unit: str = "rub",
    details: Sequence[FigureItem] = (),
) -> Figure:
    return Figure(
        value=value,
        unit=unit,
        breakdown=tuple(FigureItem(label, v) for label, v in items),  # amounts in roubles
        source=source,
        note=note,
        details=tuple(details),
    )


def _status(closed_from: date | None, as_of: date, done: bool) -> str:
    if closed_from is not None and month_first(as_of) >= closed_from:
        return STATUS_CLOSED
    return STATUS_PAID if done else STATUS_ACTIVE


def _loan_result(ob: ObligationInput, as_of: date) -> LoanResult:
    rows = schedule(ob)
    left = [r for r in rows if r.date >= as_of]
    paid = len(rows) - len(left)
    is_loan = ob.kind == KIND_LOAN
    if is_loan:
        total = ob.principal or 0
        remaining = rows[paid].balance_before if left else 0
        until = month_key(rows[-1].month) if rows else ""
    else:
        total = ob.principal or (ob.payment or 0) * (ob.payments_total or 0)
        remaining = sum(r.payment for r in left)
        until = month_key(rows[-1].month) if rows else ""
    done = remaining == 0
    status = _status(ob.closed_from, as_of, done)
    shown = remaining if status == STATUS_ACTIVE else 0
    closed_from = month_key(ob.closed_from) if ob.closed_from else None
    month_row = next((r for r in rows if r.month == month_first(as_of)), None)
    payment_value = ob.payment or 0 if status == STATUS_ACTIVE else 0
    if is_loan and month_row is not None and status == STATUS_ACTIVE:
        payment_value = month_row.payment
        parts = [
            (f"Проценты за {month_genitive(as_of.month)}", month_row.interest),
            ("Основной долг", month_row.principal),
        ]
        pay_note = "Платёж по графику: проценты идут в расходы отчёта, основной долг нет."
    else:
        parts = [("Платёж по договору", payment_value)] if payment_value else []
        pay_note = "В расходы отчёта «Прибыли и убытки» идёт целиком."
    paid_sum = total - remaining
    next_date = left[0].date if left and status == STATUS_ACTIVE else None
    details: tuple[FigureItem, ...] = ()
    if is_loan and left:
        details = (
            FigureItem(
                f"После платежа {left[0].date.day} {month_genitive(left[0].date.month)}",
                left[0].balance_after,
            ),
        )
    pct = pct_one_decimal(paid_sum, total) if total else Decimal(0)
    return LoanResult(
        id=ob.id,
        kind=ob.kind,
        name=ob.name,
        lender=ob.lender,
        principal=_fig(total, [("По договору", total)], ("manual",), "Внесено вручную."),
        remaining=_fig(
            shown,
            [("По договору", total), ("Выплачено", -paid_sum)] if shown else [],
            ("manual", "calc"),
            "Основной долг без будущих процентов."
            if is_loan
            else "Сумма оставшихся платежей по договору.",
            details=details if shown else (),
        ),
        paid_pct=_fig(
            pct,
            [("Выплачено", paid_sum), ("По договору", total)],
            ("calc",),
            f"{format_rub(paid_sum)} ÷ {format_rub(total)} = {str(pct).replace('.', ',')}%.",
            unit="pct",
        ),
        payment=_fig(payment_value, parts, ("manual", "calc"), pay_note),
        rate_pct=(ob.annual_rate_bp or 0) / 100 if is_loan else None,
        payment_day=ob.payment_day or 0,
        next_payment_date=next_date,
        until=until,
        status=status,
        closed_from=closed_from,
    )


def _equipment_result(ob: ObligationInput, as_of: date) -> EquipmentResult:
    rows = amortization_rows(ob)
    first = month_first(as_of)
    months = (ob.life_years or 0) * MONTHS_IN_YEAR
    cost = ob.cost or 0
    monthly = div_round(cost, months) if months else 0
    this = next((a for m, a in rows if m == first), 0)
    done = bool(rows) and first > rows[-1][0]
    status = _status(ob.closed_from, as_of, done)
    start, end = (month_key(rows[0][0]), month_key(rows[-1][0])) if rows else ("", "")
    return EquipmentResult(
        id=ob.id,
        name=ob.name,
        cost=_fig(cost, [("Стоимость при покупке", cost)], ("manual",), "Внесено вручную."),
        life_years=ob.life_years or 0,
        in_service_from=ob.in_service_date or as_of,
        amortization_from=start,
        amortization_to=end,
        monthly=_fig(
            monthly,
            [(ob.name, monthly)],
            ("calc",),
            f"{format_rub(cost)} ÷ {months} = {format_rub(monthly)} в месяц, с {start} по {end}.",
            details=(
                FigureItem("Стоимость", cost),
                FigureItem("Срок службы, месяцев", months, "count"),
            ),
        ),
        status=status,
        closed_from=month_key(ob.closed_from) if ob.closed_from else None,
        this_month=this if status == STATUS_ACTIVE else 0,
    )


def compute_obligations(obligations: Sequence[ObligationInput], as_of: date) -> ObligationsResult:
    """Summary for GET /v1/obligations on `as_of`: debt, monthly payment, amortization, accruals of the month."""
    order = {STATUS_ACTIVE: 0, STATUS_PAID: 1, STATUS_CLOSED: 2}
    loans = sorted(
        (_loan_result(o, as_of) for o in obligations if o.kind in (KIND_LOAN, KIND_LEASE)),
        key=lambda x: (order[x.status], x.name, x.id),
    )
    equipment = sorted(
        (_equipment_result(o, as_of) for o in obligations if o.kind == KIND_EQUIPMENT),
        key=lambda x: (order[x.status], x.name, x.id),
    )
    month = month_first(as_of)
    charges = compute_obligation_charges(obligations, month)
    by_kind = {CHARGE_LOAN: 0, CHARGE_LEASE: 0, CHARGE_AMORTIZATION: 0}
    for c in charges:
        by_kind[c.kind] += c.amount
    active_loans = [x for x in loans if x.status == STATUS_ACTIVE]
    active_eq = [x for x in equipment if x.status == STATUS_ACTIVE]
    label = month_name(month.year, month.month)
    return ObligationsResult(
        as_of=as_of,
        month=month_key(month),
        debt_total=_fig(
            sum(x.remaining.value for x in loans),
            [(x.name, int(x.remaining.value)) for x in active_loans],
            ("manual",),
            "Остаток к выплате на сегодня: по кредиту основной долг без будущих процентов, по лизингу оставшиеся платежи.",
        ),
        monthly_payment=_fig(
            sum(x.payment.value for x in active_loans),
            [(x.name, int(x.payment.value)) for x in active_loans],
            ("manual",),
            "Платежи стоят в платёжном календаре в свой день.",
        ),
        amortization_month=_fig(
            sum(x.this_month for x in active_eq),
            [(x.name, x.this_month) for x in active_eq],
            ("calc",),
            "Стоимость, делённая на срок службы в месяцах. Деньги со счёта не уходят, но входят в строку «Обязательства и амортизация» отчёта.",
        ),
        charges_month=_fig(
            sum(by_kind.values()),
            [
                ("Проценты по кредиту", by_kind[CHARGE_LOAN]),
                ("Лизинг (платёж целиком)", by_kind[CHARGE_LEASE]),
                ("Амортизация оборудования", by_kind[CHARGE_AMORTIZATION]),
            ],
            ("calc",),
            f"То же число в строке «Обязательства и амортизация» отчёта за {label}. Основной долг кредита расходом не считается.",
        ),
        loans=tuple(loans),
        equipment=tuple(equipment),
    )
