"""Engine results of the reports (stage 3) to API models. No arithmetic here: every number is the engine's."""

from datetime import date, datetime

from app.schemas import FigureItemOut, figure_out
from app.schemas_reports import (
    ExpiringRowOut,
    IdleBucketOut,
    IdleItemOut,
    NormBoundsOut,
    NormItemOut,
    NormOut,
    PeriodOut,
    PnlDirectionOut,
    PnlOut,
    PnlRowOut,
    StockOut,
    WrittenOffRowOut,
)
from engine.norm import NormBounds, NormItem, NormResult, NormShare
from engine.pnl import DirectionRow, PnlResult, PnlRow
from engine.report_facts import Period
from engine.stock import ExpiringRow, IdleBucket, IdleItem, StockResult, WrittenOffRow


def period_out(period: Period) -> PeriodOut:
    first = date(int(period.month[:4]), int(period.month[5:7]), 1)
    return PeriodOut(
        month=period.month,
        status=period.status,
        from_=first,
        to=period.to,
        first_month=period.first_month,
    )


# ------------------------------------------------------------------ P&L
def _row_out(row: PnlRow) -> PnlRowOut:
    return PnlRowOut(
        key=row.key,
        label=row.label,
        kind=row.kind,
        amount=figure_out(row.amount),
        share_pct=figure_out(row.share_pct) if row.share_pct is not None else None,
        warning=row.warning,
        children=[_row_out(c) for c in row.children] if row.children is not None else None,
    )


def _direction_out(row: DirectionRow) -> PnlDirectionOut:
    return PnlDirectionOut(
        direction=row.direction,
        label=row.label,
        revenue=figure_out(row.revenue),
        revenue_share_pct=figure_out(row.revenue_share_pct),
        direct_costs=figure_out(row.direct_costs),
        margin=figure_out(row.margin),
        margin_pct=figure_out(row.margin_pct),
    )


def pnl_out(result: PnlResult, *, view: str, as_of: date, data_as_of: datetime | None) -> PnlOut:
    with_directions = view == "direction" and result.directions is not None
    return PnlOut(
        month=result.period.month,
        view="direction" if with_directions else "clinic",
        as_of=as_of,
        data_as_of=data_as_of,
        period=period_out(result.period),
        status=result.status,
        partial_reasons=list(result.partial_reasons),
        headline=result.headline,
        rows=[_row_out(r) for r in result.rows],
        unclassified=figure_out(result.unclassified),
        unclassified_count=result.unclassified_count,
        directions=[_direction_out(d) for d in result.directions or ()]
        if with_directions
        else None,
        common_variable=(
            figure_out(result.common_variable)
            if with_directions and result.common_variable is not None
            else None
        ),
    )


# ------------------------------------------------------------------ norm
def _bounds_out(bounds: NormBounds) -> NormBoundsOut:
    return NormBoundsOut(
        min_pct=float(bounds.min_pct) if bounds.min_pct is not None else None,
        max_pct=float(bounds.max_pct) if bounds.max_pct is not None else None,
        source=bounds.source,
        breakdown=[
            FigureItemOut(label=i.label, value=int(i.value), unit="rub") for i in bounds.breakdown
        ],
        note=bounds.note,
    )


def _norm_item_out(item: NormShare) -> NormItemOut:
    rated = item if isinstance(item, NormItem) else None
    return NormItemOut(
        key=item.key,
        label=item.label,
        kind=item.kind,
        memo=item.memo,
        status=rated.status if rated else None,
        tone=rated.tone if rated else None,
        norm=_bounds_out(item.norm) if item.norm is not None else None,
        actual_pct=figure_out(item.actual_pct),
        deviation_pp=figure_out(rated.deviation_pp) if rated and rated.deviation_pp else None,
        deviation_rub=figure_out(rated.deviation_rub) if rated and rated.deviation_rub else None,
    )


def norm_out(result: NormResult, *, as_of: date, data_as_of: datetime | None) -> NormOut:
    return NormOut(
        month=result.period.month,
        as_of=as_of,
        data_as_of=data_as_of,
        period=period_out(result.period),
        status=result.status,
        partial_reasons=list(result.partial_reasons),
        headline=result.headline,
        items=[_norm_item_out(i) for i in result.items],
    )


# ------------------------------------------------------------------ stock
def _expiring_out(row: ExpiringRow) -> ExpiringRowOut:
    return ExpiringRowOut(
        item=row.item,
        expires_on=row.expires_on,
        days_left=row.days_left,
        qty=row.qty,
        amount=figure_out(row.amount),
    )


def _bucket_out(bucket: IdleBucket) -> IdleBucketOut:
    return IdleBucketOut(
        key=bucket.key,
        label=bucket.label,
        amount=figure_out(bucket.amount),
        positions=figure_out(bucket.positions),
    )


def _written_off_out(row: WrittenOffRow) -> WrittenOffRowOut:
    return WrittenOffRowOut(
        item=row.item,
        date=row.date,
        qty=row.qty,
        reason=row.reason,
        amount=figure_out(row.amount),
    )


def idle_item_out(item: IdleItem) -> IdleItemOut:
    return IdleItemOut(
        item=item.item,
        last_movement_on=item.last_movement_on,
        idle_days=item.idle_days,
        bucket=item.bucket,
        qty=item.qty,
        amount=figure_out(item.amount_figure),
    )


def stock_out(result: StockResult, *, data_as_of: datetime | None) -> StockOut:
    return StockOut(
        as_of=result.as_of,
        data_as_of=data_as_of,
        month=result.month,
        status=result.status,
        partial_reasons=list(result.partial_reasons),
        headline=result.headline,
        stock_value=figure_out(result.stock_value),
        frozen=figure_out(result.frozen),
        frozen_positions=figure_out(result.frozen_positions),
        idle_buckets=[_bucket_out(b) for b in result.idle_buckets],
        expiring_60d=figure_out(result.expiring_60d),
        expiring=[_expiring_out(r) for r in result.expiring],
        expired_on_hand=figure_out(result.expired_on_hand),
        expired_items=[_expiring_out(r) for r in result.expired_items],
        written_off_month=figure_out(result.written_off_month),
        written_off_norm=figure_out(result.written_off_norm),
        written_off_items=[_written_off_out(r) for r in result.written_off_items],
        turnover_days=figure_out(result.turnover_days),
        norm_turnover_days=result.norm_turnover_days,
    )
