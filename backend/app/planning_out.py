"""Maps the results of the stage 4 engines to the API models (docs/api-contract.md, "Планирование")."""

from datetime import datetime

from app.schemas import figure_out
from app.schemas_dash import AdviceLinkOut, AdviceOut, WhyOut
from app.schemas_planning import (
    CalendarAlertOut,
    CalendarOut,
    CalendarSummaryOut,
    CategoryRefOut,
    CounterpartyRefOut,
    DayOut,
    EquipmentOut,
    LoanOut,
    LowestOut,
    ManualPaymentOut,
    MoveSuggestionOut,
    ObligationsOut,
    PaymentOut,
    PnlMonthOut,
    PreviewOut,
    WindowOut,
)
from engine.calendar import CalendarDay, CalendarPayment, CalendarResult
from engine.calendar_alerts import CalendarAlert, MoveSuggestion
from engine.dashboard_advice import Why
from engine.obligations import EquipmentResult, LoanResult, ObligationsResult
from engine.planning_inputs import PlannedPaymentInput


def _why(w: Why) -> WhyOut:
    return WhyOut(summary=w.summary, steps=list(w.steps), sources=list(w.sources))


def _suggestion(s: MoveSuggestion) -> MoveSuggestionOut:
    return MoveSuggestionOut(
        id=s.id,
        payment_id=s.payment_id,
        payment_name=s.payment_name,
        amount=figure_out(s.amount),
        from_date=s.from_date,
        to_date=s.to_date,
        delay_days=s.delay_days,
        closes_gap=s.closes_gap,
        lowest_after=figure_out(s.lowest_after),
        text=s.text,
    )


def _alert(a: CalendarAlert) -> CalendarAlertOut:
    return CalendarAlertOut(
        id=a.id,
        date=a.date,
        date_to=a.date_to,
        severity="alert" if a.severity == "alert" else "warning",
        icon=a.icon,
        title=a.title,
        text=a.text,
        shortfall=figure_out(a.shortfall),
        suggestion=_suggestion(a.suggestion) if a.suggestion else None,
        why=_why(a.why),
    )


def _payment(p: CalendarPayment, categories: dict[str, str]) -> PaymentOut:
    counterparty = (
        CounterpartyRefOut(id=p.counterparty_key, name=p.counterparty_name or p.name)
        if p.source == "recurring" and p.counterparty_key
        else None
    )
    category = (
        CategoryRefOut(id=categories[p.category], name=p.category)
        if p.category and p.category in categories
        else None
    )
    return PaymentOut(
        id=p.id,
        name=p.name,
        category=category,
        counterparty=counterparty,
        amount=figure_out(p.amount),
        source=p.source,
        balance_after=figure_out(p.balance_after),
        max_deferral_days=p.max_deferral_days,
        moved_from=p.moved_from,
    )


def _day(d: CalendarDay, categories: dict[str, str]) -> DayOut:
    return DayOut(
        date=d.date,
        weekday=d.weekday,
        opening=figure_out(d.opening),
        income_forecast=figure_out(d.income_forecast),
        payments=[_payment(p, categories) for p in d.payments],
        closing=figure_out(d.closing),
        status=d.status,
        note=d.note,
    )


def calendar_out(
    result: CalendarResult,
    *,
    data_as_of: datetime | None,
    categories: dict[str, str],
    preview: PreviewOut | None = None,
) -> CalendarOut:
    lowest = result.summary.lowest
    return CalendarOut(
        as_of=result.as_of,
        data_as_of=data_as_of,
        window=WindowOut(**{"from": result.window_from, "to": result.window_to}),
        status=result.status,
        partial_reasons=list(result.partial_reasons),
        history_days=result.history_days,
        start_balance=figure_out(result.start_balance),
        safe_balance=figure_out(result.safe_balance),
        safe_balance_set=result.safe_balance_set,
        preview=preview,
        summary=CalendarSummaryOut(
            income=figure_out(result.summary.income),
            expense=figure_out(result.summary.expense),
            payments_count=result.summary.payments_count,
            lowest=LowestOut(
                date=lowest.date,
                balance=figure_out(lowest.balance),
                status=lowest.status,
            ),
        ),
        alerts=[_alert(a) for a in result.alerts],
        days=[_day(d, categories) for d in result.days],
    )


def manual_payment_out(p: PlannedPaymentInput, categories: dict[str, str]) -> ManualPaymentOut:
    from engine.figure import Figure, FigureItem

    amount = Figure(
        value=p.amount,
        unit="rub",
        breakdown=(FigureItem(p.name, p.amount),),
        source=("manual",),
        note="Платёж внесён вручную.",
    )
    category = (
        CategoryRefOut(id=categories[p.category], name=p.category)
        if p.category and p.category in categories
        else None
    )
    return ManualPaymentOut(
        id=p.id,
        date=p.date,
        name=p.name,
        category=category,
        amount=figure_out(amount),
        max_deferral_days=p.max_deferral_days,
    )


# ------------------------------------------------------------------ obligations
def loan_out(x: LoanResult) -> LoanOut:
    return LoanOut(
        id=x.id,
        kind=x.kind,
        name=x.name,
        lender=x.lender,
        principal=figure_out(x.principal),
        remaining=figure_out(x.remaining),
        paid_pct=figure_out(x.paid_pct),
        payment=figure_out(x.payment),
        rate_pct=x.rate_pct,
        payment_day=x.payment_day,
        next_payment_date=x.next_payment_date,
        last_payment_month=x.until,
        status=x.status,
        closed_from=x.closed_from,
    )


def equipment_out(x: EquipmentResult) -> EquipmentOut:
    return EquipmentOut(
        id=x.id,
        name=x.name,
        cost=figure_out(x.cost),
        life_years=x.life_years,
        in_service_from=x.in_service_from,
        amortization_from=x.amortization_from,
        amortization_to=x.amortization_to,
        monthly=figure_out(x.monthly),
        status=x.status,
        closed_from=x.closed_from,
    )


def obligations_out(r: ObligationsResult, share_pct: object | None = None) -> ObligationsOut:
    return ObligationsOut(
        as_of=r.as_of,
        debt_total=figure_out(r.debt_total),
        monthly_payment=figure_out(r.monthly_payment),
        monthly_payment_share_pct=share_pct,
        amortization_month=figure_out(r.amortization_month),
        pnl_month=PnlMonthOut(month=r.month, amount=figure_out(r.charges_month)),
        loans=[loan_out(x) for x in r.loans],
        equipment=[equipment_out(x) for x in r.equipment],
    )


def cash_gap_advice(alert: CalendarAlertOut) -> AdviceOut:
    text = alert.text
    if alert.suggestion is not None:
        text = f"{text} {alert.suggestion.text}"
    return AdviceOut(
        id="cash_gap",
        severity=alert.severity,
        icon=alert.icon,
        title=alert.title,
        text=text,
        why=alert.why,
        link=AdviceLinkOut(path="/planning/calendar", date=alert.date),
    )
