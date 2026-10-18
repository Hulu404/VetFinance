"""Engine results of stage 5 -> API models (docs/api-contract.md, "Прайс услуг", "Аналитика")."""

from datetime import date, datetime

from app.schemas import FigureOut, figure_out
from app.schemas_pricing import (
    DoctorLoadOut,
    EfficiencyOut,
    HourPartOut,
    PartOut,
    RoomLoadOut,
    ServiceCostOut,
    ServiceItemOut,
    ServiceRefOut,
)
from app.schemas_reports import PeriodOut
from engine.efficiency import DoctorLoad, Efficiency, RoomLoad
from engine.figure import Figure
from engine.pricing import ServiceCost


def _fig(f: Figure | None) -> FigureOut | None:
    return None if f is None else figure_out(f)


def _req(f: Figure) -> FigureOut:
    return figure_out(f)


def service_item_out(r: ServiceCost) -> ServiceItemOut:
    return ServiceItemOut.model_validate(
        {
            "id": r.id, "name": r.name, "group": r.group, "unit_label": r.unit_label, "source": r.source,
            "price": _req(r.list_price), "visits_month": _req(r.visits_month), "margin_pct": _fig(r.margin_pct),
            "monthly_profit": _fig(r.monthly_profit), "status": r.status,
        }
    )  # fmt: skip


def service_cost_out(r: ServiceCost) -> ServiceCostOut:
    ref = ServiceRefOut(
        id=r.id, name=r.name, group=r.group, unit_label=r.unit_label,
        source="manual" if r.source == "manual" else "vetmanager",
        price_source="manual" if r.price_source == "manual" else "sales",
    )  # fmt: skip
    parts = [
        PartOut.model_validate(
            {
                "key": p.key,
                "label": p.label,
                "amount": _fig(p.amount),
                "share_pct": _fig(p.share_pct),
            }
        )
        for p in r.parts
    ]
    return ServiceCostOut.model_validate(
        {
            "service": ref, "status": r.status, "missing": list(r.missing), "basis_month": r.basis_month,
            "minutes": r.minutes, "minutes_source": r.minutes_source, "price": _req(r.price),
            "net_profit": _fig(r.net_profit), "net_margin_pct": _fig(r.net_margin_pct), "parts": parts,
            "visits_month": _req(r.visits_month), "monthly_profit": _fig(r.monthly_profit),
        }
    )  # fmt: skip


def _room(r: RoomLoad) -> RoomLoadOut:
    return RoomLoadOut(
        id=r.id, name=r.name, load_pct=_req(r.load_pct), busy_hours=_req(r.busy_hours),
        available_hours=_req(r.available_hours), free_hours=_req(r.free_hours),
    )  # fmt: skip


def _doctor(d: DoctorLoad) -> DoctorLoadOut:
    return DoctorLoadOut(
        id=d.id, name=d.name, visits=_req(d.visits), load_pct=_fig(d.load_pct), busy_hours=_fig(d.busy_hours),
        available_hours=_fig(d.available_hours), free_hours=_fig(d.free_hours),
    )  # fmt: skip


def efficiency_out(
    e: Efficiency, *, as_of: date, data_as_of: datetime | None, period: PeriodOut
) -> EfficiencyOut:
    return EfficiencyOut.model_validate(
        {
            "month": e.month, "as_of": as_of, "data_as_of": data_as_of, "period": period, "status": e.status,
            "partial_reasons": list(e.partial_reasons), "headline": e.headline, "load_by": e.load_by,
            "visits": _req(e.visits), "load_pct": _fig(e.load_pct), "avg_check": _fig(e.avg_check),
            "rooms": [_room(r) for r in e.rooms], "doctors": [_doctor(d) for d in e.doctors],
            "hour_cost": _fig(e.hour_cost), "hour_margin": _fig(e.hour_margin),
            "hour_cost_parts": [
                HourPartOut.model_validate({"key": p.key, "label": p.label, "figure": _req(p.figure)})
                for p in e.hour_cost_parts
            ],
        }
    )  # fmt: skip
