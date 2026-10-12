"""Acquiring reconciliation: loads card payments and bank credits, runs the engine, builds the screen."""

from datetime import date
from typing import cast

from app.errors import not_found
from app.repo import Repository
from app.rows import TxRow
from app.schemas import figure_out
from app.schemas_acq import (
    AcquiringCreditOut,
    AcquiringDayOut,
    AcquiringMemberOut,
    AcquiringOut,
    AcquiringPaymentOut,
    AcquiringRowOut,
    AcquiringStatus,
    AcquiringSummaryOut,
    ReviewOut,
    SettlementDaysOut,
)
from app.services.transactions import month_bounds
from engine.acquiring import (
    AcquiringParams,
    BankCredit,
    CardPayment,
    DayResult,
    reconcile_acquiring,
)
from engine.acquiring_report import RowView, build_report, group_results
from engine.money import rate_bp_to_pct
from engine.pii import strip_personal_names

ACQUIRING_CATEGORY = "Выручка (эквайринг)"
SETTLEMENT_MIN_DAYS = 1
DEFAULT_CREDIT_TEXT = "Поступление по операциям эквайринга"


async def _results(repo: Repository, today: date) -> tuple[list[DayResult], list[TxRow], int]:
    rate_bp = await repo.get_acquiring_rate_bp()
    payments = await repo.list_card_payments()
    credits = await repo.list_acquiring_credits(ACQUIRING_CATEGORY)
    params = AcquiringParams(rate_bp=rate_bp)
    results = reconcile_acquiring(
        [CardPayment(p.date, p.amount) for p in payments],
        [BankCredit(c.id, c.date, c.amount) for c in credits],
        params,
        as_of=today,
        bank_covered_to=await repo.bank_covered_to(),
    )
    return results, credits, rate_bp


def _row_out(row: RowView, reviewed: bool) -> AcquiringRowOut:
    return AcquiringRowOut(
        date=row.date_from,
        date_from=row.date_from,
        date_to=row.date_to,
        card_payments=figure_out(row.card_payments),
        commission=figure_out(row.commission),
        expected=figure_out(row.expected),
        credited=figure_out(row.credited) if row.credited else None,
        discrepancy=figure_out(row.discrepancy) if row.discrepancy else None,
        status=cast(AcquiringStatus, row.status),
        expected_by=row.expected_by,
        reviewed=reviewed,
        members=[
            AcquiringMemberOut(
                date=m.day,
                card_payments=figure_out(m.card_payments),
                commission=figure_out(m.commission),
                expected=figure_out(m.expected),
            )
            for m in row.members
        ],
    )


async def reconciliation(repo: Repository, month: str, today: date) -> AcquiringOut:
    month_bounds(month)  # validates the format
    results, credits, rate_bp = await _results(repo, today)
    report = build_report(results, month, rate_bp, {})
    reviewed = {r.sale_date for r in await repo.list_reviews()}
    summary = report.summary
    return AcquiringOut(
        settlement_days=SettlementDaysOut(
            min=SETTLEMENT_MIN_DAYS, max=AcquiringParams().max_delay_business_days
        ),
        rate_pct=float(rate_bp_to_pct(rate_bp)),
        bank_covered_to=await repo.bank_covered_to(),
        summary=AcquiringSummaryOut(
            card_payments=figure_out(summary.card_payments),
            commission=figure_out(summary.commission),
            credited=figure_out(summary.credited),
            discrepancy=figure_out(summary.discrepancy),
            waiting=figure_out(summary.waiting),
        ),
        days=[_row_out(r, r.date_from in reviewed) for r in report.rows],
    )


def _group_of(results: list[DayResult], day: date) -> list[DayResult]:
    for group in group_results(results):
        if any(r.sale_date == day for r in group):
            return group
    raise not_found("За этот день оплат картой нет.")


async def day_details(repo: Repository, day: date, today: date) -> AcquiringDayOut:
    results, credits, _ = await _results(repo, today)
    group = _group_of(results, day)
    days = {r.sale_date for r in group}
    first, last = group[0].sale_date, group[-1].sale_date
    payments = [
        AcquiringPaymentOut(
            date=p.date,
            description=f"Оплата картой · счёт № {_invoice_number(p.invoice_external_id)}"
            if p.invoice_external_id
            else "Оплата картой",
            amount=p.amount,
        )
        for p in await repo.list_card_payments()
        if p.date in days
    ]
    credit_ids = {r.credit_id for r in group if r.credit_id}
    credit_rows = [
        AcquiringCreditOut(
            date=c.date,
            description=c.description or DEFAULT_CREDIT_TEXT,
            amount=c.amount,
            transaction_id=c.id,
        )
        for c in credits
        if c.id in credit_ids
    ]
    review = next((r for r in await repo.list_reviews() if r.sale_date == first), None)
    return AcquiringDayOut(
        date_from=first,
        date_to=last,
        payments=payments,
        credits=credit_rows,
        review=ReviewOut(reviewed=review is not None, note=review.note if review else None),
    )


def _invoice_number(external_id: str) -> str:
    return external_id.rsplit(":", 1)[-1]


async def review_day(repo: Repository, day: date, note: str | None, today: date) -> AcquiringRowOut:
    results, _, rate_bp = await _results(repo, today)
    group = _group_of(results, day)
    first = group[0].sale_date
    clean = strip_personal_names(note).strip() if note else None
    await repo.save_review(first, clean or None)
    report = build_report(results, first.strftime("%Y-%m"), rate_bp, {})
    row = next(r for r in report.rows if r.date_from == first)
    return _row_out(row, True)
