"""Payment calendar and obligations (stage 4): loads the snapshot, calls the engines, maps the result to the API.

All numbers come from engine/calendar.py and engine/obligations.py. Obligations are stored as terms; the accruals of
past months are frozen in `obligation_charges` before the terms change, the engine calculates the rest.
"""

from dataclasses import dataclass, replace
from datetime import date
from typing import Any

from app.errors import ApiError, not_found, validation_fields
from app.planning_out import (
    calendar_out,
    cash_gap_advice,
    equipment_out,
    loan_out,
    manual_payment_out,
    obligations_out,
)
from app.repo import Repository
from app.schemas import FigureOut, figure_out
from app.schemas_dash import AdviceOut
from app.schemas_planning import (
    CalendarOut,
    CounterpartyOut,
    EquipmentOut,
    LoanOut,
    ManualPaymentBody,
    ManualPaymentOut,
    ObligationsOut,
    PreviewOut,
)
from app.services.obligation_input import check_cross, validate_create, validate_patch
from engine.balance import AccountInput, TransactionInput
from engine.calendar import CalendarResult, compute_calendar
from engine.dashboard_month import sales_totals
from engine.figure import Figure, FigureItem
from engine.money import pct_one_decimal, pct_to_rate_bp
from engine.obligations import (
    add_months,
    compute_obligation_charges,
    compute_obligations,
    loan_schedule,
    month_first,
    month_key,
    nominal_date,
    shift_off_day,
)
from engine.planning_inputs import (
    KIND_EQUIPMENT,
    KIND_LOAN,
    CounterpartyTermsInput,
    ObligationInput,
    PaymentMoveInput,
    PlannedPaymentInput,
    counterparty_key,
)
from engine.report_facts import last_closed_month, month_bounds
from engine.reports_inputs import CategoryInput, ObligationChargeInput

WINDOW_DAYS = 22
MAX_SCHEDULE_PAYMENTS = 600
EARLIEST = date(2000, 1, 1)
MAX_DEFERRAL_DAYS = 30
NAME_MAX = 80
MONEY_MAX = 10**12
MAX_FREEZE_MONTHS = 1200


@dataclass(frozen=True)
class Snapshot:
    accounts: list[AccountInput]
    transactions: list[TransactionInput]
    categories: list[CategoryInput]
    category_ids: dict[str, str]
    obligations: list[ObligationInput]
    planned: list[PlannedPaymentInput]
    terms: list[CounterpartyTermsInput]
    safe_balance: int


async def load_snapshot(repo: Repository, as_of: date) -> Snapshot:
    from app.services.reports import category_inputs  # reports import this module too

    rows = await repo.list_categories()
    return Snapshot(
        accounts=await repo.list_accounts(),
        transactions=await repo.list_transactions(as_of),
        categories=category_inputs(rows),
        category_ids={c.name: c.id for c in rows},
        obligations=await repo.list_obligation_inputs(),
        planned=await repo.list_planned_payments(),
        terms=await repo.list_counterparty_terms(),
        safe_balance=(await repo.get_clinic()).safe_balance,
    )


def _compute(
    snap: Snapshot, as_of: date, moves: tuple[PaymentMoveInput, ...] = ()
) -> CalendarResult:
    return compute_calendar(
        snap.accounts, snap.transactions, snap.categories, snap.obligations, snap.planned,
        snap.terms, snap.safe_balance, as_of, WINDOW_DAYS, moves,
    )  # fmt: skip


async def build_calendar(repo: Repository, as_of: date, preview: str | None = None) -> CalendarOut:
    snap = await load_snapshot(repo, as_of)
    result = _compute(snap, as_of)
    marker: PreviewOut | None = None
    if preview is not None:
        suggestion = next(
            (a.suggestion for a in result.alerts if a.suggestion and a.suggestion.id == preview),
            None,
        )
        if suggestion is None:
            raise validation_fields({"preview": "invalid"})
        move = PaymentMoveInput(
            suggestion.payment_name,
            "",
            suggestion.from_date,
            suggestion.to_date,
            suggestion.payment_id,
        )
        result = _compute(snap, as_of, (move,))
        marker = PreviewOut(
            suggestion_id=suggestion.id,
            payment_id=suggestion.payment_id,
            from_date=suggestion.from_date,
            to_date=suggestion.to_date,
        )
    return calendar_out(
        result, data_as_of=await repo.last_data_at(), categories=snap.category_ids, preview=marker
    )


async def cash_gap(repo: Repository, as_of: date) -> AdviceOut | None:
    snap = await load_snapshot(repo, as_of)
    alerts = _compute(snap, as_of).alerts
    if not alerts:
        return None
    out = calendar_out(_compute(snap, as_of), data_as_of=None, categories=snap.category_ids).alerts[
        0
    ]
    return cash_gap_advice(out)


# ------------------------------------------------------------------ manual payments
async def add_manual_payment(
    repo: Repository, body: ManualPaymentBody, as_of: date
) -> ManualPaymentOut:
    fields: dict[str, str] = {}
    if not body.name.strip():
        fields["name"] = "required"
    elif len(body.name) > NAME_MAX:
        fields["name"] = "too_long"
    if body.amount <= 0:
        fields["amount"] = "must_be_positive"
    elif body.amount > MONEY_MAX:
        fields["amount"] = "too_large"
    if not 0 <= body.max_deferral_days <= MAX_DEFERRAL_DAYS:
        fields["max_deferral_days"] = "out_of_range"
    last = as_of.fromordinal(as_of.toordinal() + WINDOW_DAYS - 1)
    if not as_of <= body.date <= last:
        fields["date"] = "out_of_window"
    categories = {c.id: c.name for c in await repo.list_categories()}
    if body.category_id is not None and body.category_id not in categories:
        fields["category_id"] = "invalid"
    if fields:
        raise validation_fields(fields)
    row = await repo.add_planned_payment(
        body.date, body.name.strip(), body.amount, body.category_id, body.max_deferral_days
    )
    return manual_payment_out(row, {name: cid for cid, name in categories.items()})


async def delete_manual_payment(repo: Repository, payment_id: str) -> None:
    if not await repo.delete_planned_payment(payment_id):
        raise not_found("Платёж не найден.")


# ------------------------------------------------------------------ counterparties
async def set_deferral(repo: Repository, counterparty_id: str, days: int) -> CounterpartyOut:
    if not 0 <= days <= MAX_DEFERRAL_DAYS:
        raise validation_fields({"max_deferral_days": "out_of_range"})
    today_names: dict[str, str] = {}
    for t in await repo.list_transactions(date.max):
        if t.kind == "out" and t.counterparty_name:
            today_names[counterparty_key(t.counterparty_inn or None, t.counterparty_name)] = (
                t.counterparty_name
            )
    stored = {c.inn: c.name for c in await repo.list_counterparty_terms()}
    name = today_names.get(counterparty_id) or stored.get(counterparty_id)
    if name is None:
        raise not_found("Контрагент не найден.")
    await repo.set_counterparty_terms(counterparty_id, name, days)
    return CounterpartyOut(id=counterparty_id, name=name, max_deferral_days=days)


# ------------------------------------------------------------------ obligations: terms
def _next_payment(today: date, payment_day: int) -> date:
    """First payment day not earlier than `today` (weekend moved to the previous working day)."""
    first = month_first(today)
    for step in range(2):
        month = add_months(first, step)
        day = shift_off_day(nominal_date(month, payment_day))
        if day >= today:
            return day
    raise AssertionError("unreachable")  # pragma: no cover


def _debt_terms(
    kind: str,
    *,
    principal: int,
    remaining: int,
    rate_pct: float | None,
    payment: int,
    payment_day: int,
    today: date,
) -> dict[str, Any]:
    """Columns of a loan or a lease whose schedule starts with `remaining` at the next payment day."""
    start = _next_payment(today, payment_day)
    terms: dict[str, Any] = {
        "principal": principal,
        "payment": payment,
        "payment_day": payment_day,
        "first_payment_date": start,
        "start_balance": remaining,
        "annual_rate_bp": pct_to_rate_bp(repr(rate_pct))
        if kind == KIND_LOAN and rate_pct is not None
        else None,
    }
    probe = ObligationInput(
        id="", kind=kind, name="", payments_total=MAX_SCHEDULE_PAYMENTS, **terms
    )
    if kind == KIND_LOAN:
        count = len(loan_schedule(probe))
    else:
        count = max(1, -(-remaining // payment))
    terms["payments_total"] = max(1, count)
    return terms


def _new_obligation(data: dict[str, Any], today: date) -> ObligationInput:
    kind = data["kind"]
    base = ObligationInput(
        id="",
        kind=kind,
        name=data["name"].strip(),
        lender=data.get("lender") or None,
    )
    if kind == KIND_EQUIPMENT:
        return replace(
            base,
            cost=data["cost"],
            life_years=data["life_years"],
            in_service_date=data["in_service_from"],
        )
    terms = _debt_terms(
        kind,
        principal=data["principal"],
        remaining=data["remaining"],
        rate_pct=data.get("rate_pct"),
        payment=data["payment"],
        payment_day=data["payment_day"],
        today=today,
    )
    return replace(base, **terms)


def _find(obligations: list[ObligationInput], obligation_id: str) -> ObligationInput:
    row = next((o for o in obligations if o.id == obligation_id and o.closed_from is None), None)
    if row is None:
        raise not_found("Обязательство не найдено.")
    return row


async def freeze_past_charges(repo: Repository, ob: ObligationInput, today: date) -> None:
    """Write the accruals of the months before the current one, so that a change of terms does not move them."""
    current = month_first(today)
    rows: list[ObligationChargeInput] = []
    month = month_first(_first_charge_month(ob, current))
    for _ in range(MAX_FREEZE_MONTHS):
        if month >= current:
            break
        rows.extend(compute_obligation_charges([ob], month))
        month = add_months(month, 1)
    await repo.insert_charges(rows)


def _first_charge_month(ob: ObligationInput, fallback: date) -> date:
    if ob.kind == KIND_EQUIPMENT and ob.in_service_date:
        return add_months(month_first(ob.in_service_date), 1)
    if ob.first_payment_date:
        return month_first(ob.first_payment_date)
    return fallback


def _row_out(ob: ObligationInput, today: date) -> LoanOut | EquipmentOut:
    result = compute_obligations([ob], today)
    if ob.kind == KIND_EQUIPMENT:
        return equipment_out(result.equipment[0])
    return loan_out(result.loans[0])


async def create_obligation(repo: Repository, body: object, today: date) -> LoanOut | EquipmentOut:
    data = validate_create(body, today)
    row = await repo.create_obligation(_new_obligation(data, today))
    return _row_out(row, today)


_DEBT_KEYS = ("principal", "remaining", "rate_pct", "payment", "payment_day")


async def patch_obligation(
    repo: Repository, obligation_id: str, body: object, today: date
) -> LoanOut | EquipmentOut:
    current = _find(await repo.list_obligation_inputs(), obligation_id)
    data = validate_patch(body, current.kind, today)
    await freeze_past_charges(repo, current, today)
    changes: dict[str, Any] = {
        k: data[k] for k in ("name", "lender", "cost", "life_years") if k in data
    }
    if "name" in changes:
        changes["name"] = changes["name"].strip()
    if "in_service_from" in data:
        changes["in_service_date"] = data["in_service_from"]
    if current.kind != KIND_EQUIPMENT and any(k in data for k in _DEBT_KEYS):
        shown = compute_obligations([current], today)
        row = shown.loans[0]
        merged = {
            "principal": data.get("principal", current.principal or 0),
            "remaining": data.get("remaining", int(row.remaining.value)),
            "rate_pct": data.get("rate_pct", row.rate_pct),
            "payment": data.get("payment", current.payment or 0),
            "payment_day": data.get("payment_day", current.payment_day or 1),
        }
        cross, extra = check_cross(merged)
        if cross:
            error: ApiError = validation_fields(cross)
            error.details.update(extra)
            raise error
        changes.update(_debt_terms(current.kind, today=today, **merged))
    updated = await repo.update_obligation(obligation_id, changes)
    if updated is None:
        raise not_found("Обязательство не найдено.")
    return _row_out(updated, today)


async def close_obligation(repo: Repository, obligation_id: str, today: date) -> None:
    current = _find(await repo.list_obligation_inputs(), obligation_id)
    await freeze_past_charges(repo, current, today)
    if not await repo.close_obligation(obligation_id, month_first(today)):
        raise not_found("Обязательство не найдено.")


# ------------------------------------------------------------------ obligations: reading
async def _payment_share(repo: Repository, as_of: date, monthly: int) -> FigureOut | None:
    month = last_closed_month(as_of)
    first, last = month_bounds(month)
    revenue = sales_totals(await repo.list_sales(first, last), first, last).revenue
    if revenue <= 0 or monthly <= 0:
        return None
    pct = pct_one_decimal(monthly, revenue)
    label = f"Выручка {month_key(month)}"
    figure = Figure(
        value=pct,
        unit="pct",
        breakdown=(FigureItem("Платёж в месяц", monthly), FigureItem(label, revenue)),
        source=("calc",),
        note=f"{monthly} ÷ {revenue}: выручка последнего закрытого месяца.",
    )
    return figure_out(figure)


async def build_obligations(repo: Repository, as_of: date) -> ObligationsOut:
    result = compute_obligations(await repo.list_obligation_inputs(), as_of)
    share = await _payment_share(repo, as_of, int(result.monthly_payment.value))
    return obligations_out(result, share)


# ------------------------------------------------------------------ P&L accruals
async def charges_for_report(repo: Repository, month: date) -> list[ObligationChargeInput]:
    """Frozen accruals of the table plus the ones the engine calculates for obligations that have none this month."""
    stored = await repo.list_obligation_charges()
    month_str = month_key(month_first(month))
    have = {c.obligation_id for c in stored if c.month == month_str}
    computed = compute_obligation_charges(await repo.list_obligation_inputs(), month)
    return stored + [c for c in computed if c.obligation_id not in have]
