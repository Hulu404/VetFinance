"""The totals of a month's P&L in the form the stage 5 engines read (`PnlMonthInput`)."""

from engine.pricing_inputs import LINE_KIND_MATERIALS, PnlLineInput, PnlMonthInput
from engine.report_facts import MonthFacts, Totals
from engine.reports_inputs import TYPE_FIXED, TYPE_VARIABLE


def pnl_month_input(month_key: str, facts: MonthFacts, totals: Totals) -> PnlMonthInput:
    """Revenue, variable costs, the percent paid to doctors, the fixed lines (the article already inside the
    techcards is marked `materials`) and the obligation charges of one month."""
    payouts = sum(
        c.amount
        for c in facts.costs
        if c.type == TYPE_VARIABLE and c.category is not None and c.category.doctor_percent
    )
    fixed = []
    for c in sorted(facts.costs, key=lambda c: (-c.amount, c.name)):
        if c.type != TYPE_FIXED:
            continue
        cat = c.category
        kind = (
            LINE_KIND_MATERIALS
            if cat is not None and cat.in_service_recipes
            else ("payroll" if cat is not None and cat.payroll else "other")
        )
        fixed.append(PnlLineInput(c.name, c.amount, kind))
    return PnlMonthInput(
        month=month_key,
        revenue=totals.revenue,
        variable_total=totals.variable,
        marginal_profit=totals.marginal,
        doctor_percent_payouts=payouts,
        acquiring_fee=facts.commission,
        taxes=totals.taxes,
        fixed_lines=tuple(fixed),
        obligation_lines=tuple(
            PnlLineInput(n, a, "obligations") for n, a in totals.obligation_lines
        ),
    )
