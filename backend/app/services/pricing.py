"""Stage 5: price list, cost of a service, techcard, stock prices, efficiency (docs/api-contract.md).

Loads the snapshot from the repository, calls the engines (engine/pricing.py, engine/efficiency.py) and maps the
result to the API models. Nothing is calculated here.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from app.errors import forbidden, not_found, validation_fields
from app.pricing_input import (
    parse_month,
    parse_recipe,
    parse_service_create,
    parse_service_patch,
    parse_settings,
)
from app.pricing_out import efficiency_out, service_cost_out, service_item_out
from app.repo import Repository
from app.rows import ServiceRecord
from app.schemas import figure_out
from app.schemas_pricing import (
    DoctorHoursOut,
    EfficiencyOut,
    EfficiencySettingsOut,
    RecipeDefaultsOut,
    RecipeItemOut,
    RecipeOut,
    RecipeServiceOut,
    ServiceCostOut,
    ServiceItemOut,
    ServicesOut,
    StockItemOut,
    StockItemsOut,
)
from app.schemas_reports import PeriodOut
from app.services import reports
from engine.dashboard_inputs import SaleInput
from engine.efficiency import Efficiency, compute_efficiency
from engine.pricing import (
    PRICE_WINDOW_DAYS,
    PriceList,
    ServiceCost,
    compute_price_list,
    compute_service_cost,
    item_unit_costs,
    normalize_name,
    recipe_defaults,
)
from engine.pricing_inputs import (
    ManualServiceInput,
    PnlMonthInput,
    ServiceSettingInput,
    StockBatchInput,
    StockItemInput,
    TechcardInput,
    TechcardLineInput,
)
from engine.report_facts import MonthFacts, last_closed_month, month_bounds, month_key

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
SORTS = ("margin", "profit")
ORDERS = ("asc", "desc")
FILTERS = ("all", "loss", "no_recipe")


@dataclass(frozen=True)
class Snapshot:
    as_of: date
    month: date  # first day of the basis month
    pnl: PnlMonthInput
    facts: MonthFacts
    efficiency: Efficiency
    avg_minutes: int
    sales: list[SaleInput]
    catalog: list[ServiceRecord]
    settings: list[ServiceSettingInput]
    techcards: list[TechcardInput]
    items: list[StockItemInput]
    batches: list[StockBatchInput]


async def snapshot(repo: Repository, as_of: date, month: date | None = None) -> Snapshot:
    """Everything the engines need for the basis month (by default the last closed one)."""
    first = month or last_closed_month(as_of)
    last = month_bounds(first)[1]
    pnl, facts = await reports.pnl_month_data(repo, reports.Window(as_of, first))
    avg = await repo.get_avg_visit_minutes()
    eff = compute_efficiency(
        await repo.list_visits(first, last), [], await repo.list_doctor_inputs(), await repo.list_rooms(),
        await repo.list_room_bookings(first, last), pnl, avg, month_key(first), as_of,
    )  # fmt: skip
    window_start = min(first, as_of - timedelta(days=PRICE_WINDOW_DAYS))
    return Snapshot(
        as_of, first, pnl, facts, eff, avg, await repo.list_pricing_sales(window_start, max(as_of, last)),
        await repo.list_services(), await repo.list_service_settings(), await repo.list_techcards(),
        await repo.list_pricing_stock_items(), await repo.list_pricing_batches(),
    )  # fmt: skip


def _hour_cost(s: Snapshot) -> int | None:
    return None if s.efficiency.hour_cost is None else int(s.efficiency.hour_cost.value)


def _price_list(s: Snapshot, sort: str = "margin", descending: bool = False) -> PriceList:
    manual = [
        ManualServiceInput(r.id, r.name, r.manual_price or 0)
        for r in s.catalog
        if r.source == "manual"
    ]
    return compute_price_list(
        s.sales, manual, s.settings, s.techcards, s.items, s.batches, s.pnl, _hour_cost(s), s.avg_minutes,
        month_key(s.month), s.as_of, sort, descending,
    )  # fmt: skip


def _card(s: Snapshot, service_id: str) -> ServiceCost | None:
    manual = [
        ManualServiceInput(r.id, r.name, r.manual_price or 0)
        for r in s.catalog
        if r.source == "manual"
    ]
    return compute_service_cost(
        s.sales, manual, s.settings, s.techcards, s.items, s.batches, s.pnl, _hour_cost(s), s.avg_minutes,
        month_key(s.month), s.as_of, service_id,
    )  # fmt: skip


def _offset(cursor: str | None) -> int:
    if cursor is None:
        return 0
    if not cursor.isdigit():
        raise validation_fields({"cursor": "invalid"})
    return int(cursor)


def _check_enum(name: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise validation_fields({name: "invalid"})


def _check_limit(limit: int) -> None:
    if limit < 1:
        raise validation_fields({"limit": "must_be_positive"})
    if limit > MAX_LIMIT:
        raise validation_fields({"limit": "too_large"})


async def list_services(
    repo: Repository,
    as_of: date,
    sort: str,
    order: str,
    flt: str,
    q: str | None,
    limit: int,
    cursor: str | None,
) -> ServicesOut:
    _check_enum("sort", sort, SORTS)
    _check_enum("order", order, ORDERS)
    _check_enum("filter", flt, FILTERS)
    _check_limit(limit)
    start = _offset(cursor)
    s = await snapshot(repo, as_of)
    result = _price_list(s, sort, order == "desc")
    items = list(result.items)
    if flt == "loss":
        items = [x for x in items if x.net_profit is not None and x.net_profit.value < 0]
    elif flt == "no_recipe":
        items = [x for x in items if x.status == "no_recipe"]
    if q and q.strip():
        needle = normalize_name(q)
        items = [x for x in items if needle in normalize_name(x.name)]
    page = items[start : start + limit]
    more = str(start + limit) if start + limit < len(items) else None
    return ServicesOut.model_validate(
        {
            "basis_month": result.basis_month, "headline": result.headline,
            "counts": {"all": result.counts.all, "loss": result.counts.loss, "no_recipe": result.counts.no_recipe},
            "items": [service_item_out(x) for x in page], "next_cursor": more,
        }
    )  # fmt: skip


async def _record(repo: Repository, service_id: str) -> ServiceRecord:
    rec = await repo.get_service(service_id)
    if rec is None:
        raise not_found("Услуга не найдена.")
    return rec


async def service_cost(repo: Repository, as_of: date, service_id: str) -> ServiceCostOut:
    await _record(repo, service_id)
    card = _card(await snapshot(repo, as_of), service_id)
    if card is None:
        raise not_found("Услуги нет в прайсе: по ней не было продаж за 90 дней.")
    return service_cost_out(card)


async def _taken_names(repo: Repository, except_id: str | None = None) -> set[str]:
    return {normalize_name(r.name) for r in await repo.list_services() if r.id != except_id}


async def create_service(repo: Repository, as_of: date, body: Any) -> ServiceItemOut:
    parsed = parse_service_create(body)
    if normalize_name(parsed.name) in await _taken_names(repo):
        raise validation_fields({"name": "duplicate_name"})
    rec = await repo.create_manual_service(parsed.name, parsed.group, parsed.price)
    card = next((x for x in _price_list(await snapshot(repo, as_of)).items if x.id == rec.id), None)
    if card is None:  # cannot happen: a manual service always has a price
        raise not_found("Услуга не найдена.")
    return service_item_out(card)


async def _manual_record(repo: Repository, service_id: str) -> ServiceRecord:
    rec = await _record(repo, service_id)
    if rec.source != "manual":
        raise forbidden("Услугу из Ветменеджера нельзя изменить или удалить.")
    return rec


async def patch_service(repo: Repository, service_id: str, body: Any) -> None:
    await _manual_record(repo, service_id)
    parsed = parse_service_patch(body)
    if parsed.name is not None and normalize_name(parsed.name) in await _taken_names(
        repo, service_id
    ):
        raise validation_fields({"name": "duplicate_name"})
    changes: dict[str, Any] = {}
    if parsed.name is not None:
        changes["name"] = parsed.name
    if parsed.group_given:
        changes["group"] = parsed.group
    if parsed.price is not None:
        changes["price"] = parsed.price
    await repo.update_manual_service(service_id, changes)


async def delete_service(repo: Repository, service_id: str) -> None:
    await _manual_record(repo, service_id)
    await repo.delete_manual_service(service_id)


# ------------------------------------------------------------------ techcard
async def get_recipe(repo: Repository, as_of: date, service_id: str) -> RecipeOut:
    rec = await _record(repo, service_id)
    s = await snapshot(repo, as_of)
    setting = next((x for x in s.settings if x.service_id == service_id), None)
    card = next((x for x in s.techcards if x.service_id == service_id), None)
    costs = item_unit_costs(s.items, s.batches, as_of)
    names = {i.id: i for i in s.items}
    items = [
        RecipeItemOut(
            item_id=line.item_id, name=names[line.item_id].name, unit=names[line.item_id].unit,
            group=line.part, qty=float(line.qty),
            unit_cost=None if costs.get(line.item_id) is None else figure_out(costs[line.item_id]),  # type: ignore[arg-type]
        )
        for line in (card.lines if card else ())
        if line.item_id in names
    ]  # fmt: skip
    minutes_fig, pct_fig = recipe_defaults(s.sales, s.pnl, month_key(s.month), s.avg_minutes)
    bp = setting.doctor_pct_bp if setting else None
    return RecipeOut(
        service=RecipeServiceOut(id=rec.id, name=rec.name), has_recipe=card is not None,
        minutes=setting.minutes if setting else None, doctor_pct=None if bp is None else bp / 100, items=items,
        defaults=RecipeDefaultsOut(
            minutes=figure_out(minutes_fig), doctor_pct=None if pct_fig is None else figure_out(pct_fig)
        ),
    )  # fmt: skip


async def put_recipe(repo: Repository, as_of: date, service_id: str, body: Any) -> RecipeOut:
    await _record(repo, service_id)  # 404 comes before the check of the body
    known = {i.id for i in await repo.list_pricing_stock_items()}
    parsed = parse_recipe(body, known)
    bp = None if parsed.doctor_pct is None else int(parsed.doctor_pct * 100)
    lines = [TechcardLineInput(x.item_id, x.qty, x.group) for x in parsed.items]
    await repo.save_recipe(service_id, parsed.minutes, bp, lines)
    return await get_recipe(repo, as_of, service_id)


async def stock_items(
    repo: Repository, as_of: date, q: str | None, limit: int, cursor: str | None
) -> StockItemsOut:
    _check_limit(limit)
    start = _offset(cursor)
    items = await repo.list_pricing_stock_items()
    if q and q.strip():
        needle = normalize_name(q)
        items = [x for x in items if needle in normalize_name(x.name)]
    costs = item_unit_costs(items, await repo.list_pricing_batches(), as_of)
    page = items[start : start + limit]
    more = str(start + limit) if start + limit < len(items) else None
    return StockItemsOut(
        items=[
            StockItemOut(
                id=x.id, name=x.name, unit=x.unit,
                unit_cost=None if costs.get(x.id) is None else figure_out(costs[x.id]),  # type: ignore[arg-type]
            )
            for x in page
        ],
        next_cursor=more,
    )  # fmt: skip


# ------------------------------------------------------------------ efficiency
async def efficiency(repo: Repository, as_of: date, month: str | None) -> EfficiencyOut:
    parse_month(month)
    last_closed = last_closed_month(as_of)
    first = last_closed if month is None else date(int(month[:4]), int(month[5:]), 1)
    if first > last_closed:
        raise validation_fields({"month": "in_future"})
    s = await snapshot(repo, as_of, first)
    period = PeriodOut(
        month=month_key(first), status="closed", from_=first, to=None, first_month=s.facts.period.first_month
    )  # fmt: skip
    return efficiency_out(
        s.efficiency, as_of=as_of, data_as_of=await repo.last_data_at(), period=period
    )


async def get_settings(repo: Repository) -> EfficiencySettingsOut:
    doctors = await repo.list_doctor_inputs()
    return EfficiencySettingsOut(
        avg_visit_minutes=await repo.get_avg_visit_minutes(),
        doctors=[
            DoctorHoursOut(
                id=d.id, name=d.name, hours_per_week=None if d.hours_per_week is None else float(d.hours_per_week)
            )
            for d in doctors
        ],
    )  # fmt: skip


async def put_settings(repo: Repository, body: Any) -> EfficiencySettingsOut:
    known = {d.id for d in await repo.list_doctor_inputs()}
    parsed = parse_settings(body, known)
    await repo.set_avg_visit_minutes(parsed.avg_visit_minutes)
    hours: dict[str, Decimal | None] = {d.id: d.hours_per_week for d in parsed.doctors}
    await repo.set_doctor_hours(hours)
    return await get_settings(repo)
