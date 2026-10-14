"""API models of GET /v1/dashboard (stage 2). Money is int kopecks, percents are numbers with one decimal."""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas import FigureOut, figure_out
from engine.dashboard import Advice, DashboardResult


def _is_none(value: object) -> bool:
    return value is None


Source = Literal["bank", "vetmanager", "bot", "manual", "calc"]


class TrendPointOut(BaseModel):
    date: date
    value: int


class TrendInfoOut(BaseModel):
    note: str
    source: list[Source]


class WhyOut(BaseModel):
    summary: str
    steps: list[str]
    sources: list[str]


class AdviceOut(BaseModel):
    id: str
    severity: Literal["alert", "warning", "good"]
    icon: str
    title: str
    text: str
    why: WhyOut


class DashboardBalanceOut(BaseModel):
    total: FigureOut
    bank: FigureOut
    cash: FigureOut
    week_change: FigureOut | None  # null: no history for 7 days
    week_change_pct: FigureOut | None
    runway_days: FigureOut | None = Field(default=None, exclude_if=_is_none)  # omitted: no expenses


class DashboardMonthOut(BaseModel):
    days_passed: int
    days_total: int
    revenue: FigureOut
    expenses: FigureOut
    profit: FigureOut
    profit_margin_pct: FigureOut | None = Field(
        default=None, exclude_if=_is_none
    )  # omitted: no revenue
    visits: FigureOut
    avg_check: FigureOut | None = Field(default=None, exclude_if=_is_none)  # omitted: no invoices


class DashboardOut(BaseModel):
    as_of: date
    data_as_of: datetime | None
    data_stale: bool
    balance: DashboardBalanceOut
    month: DashboardMonthOut
    balance_trend: list[TrendPointOut]
    balance_trend_info: TrendInfoOut
    advice: list[AdviceOut]
    advice_status: Literal["ready", "not_enough_data"]  # not_enough_data: under a week of history


def _optional(figure: Any) -> FigureOut | None:
    return figure_out(figure) if figure is not None else None


def _advice_out(a: Advice) -> AdviceOut:
    return AdviceOut(
        id=a.id,
        severity=a.severity,
        icon=a.icon,
        title=a.title,
        text=a.text,
        why=WhyOut(summary=a.why.summary, steps=list(a.why.steps), sources=list(a.why.sources)),
    )


def dashboard_out(
    result: DashboardResult, *, data_as_of: datetime | None, data_stale: bool
) -> DashboardOut:
    b, m = result.balance, result.month
    return DashboardOut(
        as_of=result.as_of,
        data_as_of=data_as_of,
        data_stale=data_stale,
        balance=DashboardBalanceOut(
            total=figure_out(b.total),
            bank=figure_out(b.bank),
            cash=figure_out(b.cash),
            week_change=_optional(b.week_change),
            week_change_pct=_optional(b.week_change_pct),
            runway_days=_optional(b.runway_days),
        ),
        month=DashboardMonthOut(
            days_passed=m.days_passed,
            days_total=m.days_total,
            revenue=figure_out(m.revenue),
            expenses=figure_out(m.expenses),
            profit=figure_out(m.profit),
            profit_margin_pct=_optional(m.profit_margin_pct),
            visits=figure_out(m.visits),
            avg_check=_optional(m.avg_check),
        ),
        balance_trend=[TrendPointOut(date=p.date, value=p.value) for p in result.balance_trend],
        balance_trend_info=TrendInfoOut.model_validate(
            {
                "note": result.balance_trend_info.note,
                "source": list(result.balance_trend_info.source),
            }
        ),
        advice=[_advice_out(a) for a in result.advice],
        advice_status=result.advice_status,
    )
