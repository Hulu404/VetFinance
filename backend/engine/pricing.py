"""Price list and cost of a service (functions 11, 12): price, seven parts, net profit, margin.

Pure functions, rules P1-P14 of tests/golden/set06/README.md. Every part is rounded once from exact fractions
(engine/money.py); the shares are cut in tenths of a percent so that they add up to exactly 100,0.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction

from engine.dashboard_inputs import LINE_SERVICE, SALE_EXEC, SaleInput
from engine.figure import Figure, ordered_sources
from engine.money import div_round, format_rub, pct_one_decimal
from engine.pricing_figures import (
    PART_KEYS,
    PART_LABELS,
    PricedLine,
    acquiring_figure,
    count_figure,
    doctor_pay_figure,
    fixed_figure,
    headline,
    item,
    largest_remainder,
    material_figure,
    month_word,
    num,
    rub_figure,
    share_figure,
    simple_share,
    taxes_figure,
    unit_price_text,
)
from engine.pricing_inputs import (
    ManualServiceInput,
    PnlMonthInput,
    ServiceSettingInput,
    StockBatchInput,
    StockItemInput,
    TechcardInput,
)
from engine.ru import format_date

PRICE_WINDOW_DAYS = 90
BASIS_POINTS = 10_000
MINUTES_IN_HOUR = 60
MATERIAL_PARTS = ("drugs", "anesthesia", "supplies")
UNIT_LABELS = {"S6": "сутки"}


@dataclass(frozen=True)
class PartRow:
    key: str
    label: str
    amount: Figure | None
    share_pct: Figure | None


@dataclass(frozen=True)
class ServiceCost:
    id: str
    name: str
    group: str | None
    unit_label: str
    source: str  # vetmanager | manual
    price_source: str  # sales | manual
    status: str  # ok | no_recipe | partial
    missing: tuple[str, ...]
    basis_month: str
    minutes: int
    minutes_source: str  # own | clinic_average
    price: Figure  # the card: split into the parts and the profit
    list_price: Figure  # the list row: the average price of the sales, or the one the owner entered
    net_profit: Figure | None
    net_margin_pct: Figure | None
    margin_pct: Figure | None
    parts: tuple[PartRow, ...]
    visits_month: Figure
    monthly_profit: Figure | None
    sort_margin: Fraction | None  # exact net_profit / price, for the order only


@dataclass(frozen=True)
class Counts:
    all: int
    loss: int
    no_recipe: int


@dataclass(frozen=True)
class PriceList:
    basis_month: str
    headline: str | None
    counts: Counts
    items: tuple[ServiceCost, ...]


@dataclass(frozen=True)
class _Entry:
    id: str
    name: str
    group: str | None
    source: str
    price: int
    price_source: str
    visits: int


def normalize_name(name: str) -> str:
    """The key of a service name: case, extra spaces and ё/е do not matter."""
    return " ".join(name.split()).casefold().replace("ё", "е")


def _whole(qty: Fraction) -> int:
    return div_round(qty.numerator, qty.denominator)


def _collect(sales: Sequence[SaleInput], month: str, as_of: date) -> tuple[dict[str, _Entry], int]:
    first, last = as_of - timedelta(days=PRICE_WINDOW_DAYS), as_of - timedelta(days=1)
    amount: dict[str, int] = {}
    qty: dict[str, Fraction] = {}
    month_qty: dict[str, Fraction] = {}
    names: dict[str, tuple[date, str, str]] = {}
    revenue = 0
    for sale in sales:
        if sale.status != SALE_EXEC:
            continue
        for line in sale.lines:
            if line.kind != LINE_SERVICE:
                continue
            if sale.date.strftime("%Y-%m") == month:
                revenue += line.amount
                if line.service_id:
                    month_qty[line.service_id] = month_qty.get(
                        line.service_id, Fraction(0)
                    ) + Fraction(line.qty)
            if line.service_id and first <= sale.date <= last:
                sid = line.service_id
                amount[sid] = amount.get(sid, 0) + line.amount
                qty[sid] = qty.get(sid, Fraction(0)) + Fraction(line.qty)
                names[sid] = max(
                    names.get(sid, (date.min, "", "")), (sale.date, sale.id, line.name)
                )
    entries = {
        sid: _Entry(sid, names[sid][2], None, "vetmanager", div_round(amount[sid] * q.denominator, q.numerator),
                    "sales", _whole(month_qty.get(sid, Fraction(0))))
        for sid, q in qty.items() if q > 0
    }  # fmt: skip
    return entries, revenue


def _entries(
    sales: Sequence[SaleInput], manual: Sequence[ManualServiceInput],
    settings: dict[str, ServiceSettingInput], month: str, as_of: date,
) -> tuple[list[_Entry], int]:  # fmt: skip
    sold, services_revenue = _collect(sales, month, as_of)
    rows = []
    for sid, e in sold.items():
        st = settings.get(sid)
        rows.append(
            _Entry(
                sid,
                (st.name if st and st.name else e.name),
                st.group if st else None,
                e.source,
                e.price,
                e.price_source,
                e.visits,
            )
        )
    taken = {normalize_name(r.name) for r in rows}
    for m in manual:
        if normalize_name(m.name) in taken:
            continue  # the same name as a sold service: it becomes that service, with the price of the sales
        st = settings.get(m.id)
        rows.append(_Entry(m.id, m.name, st.group if st else None, "manual", m.price, "manual", 0))
    return rows, services_revenue


def _item_prices(
    items: Sequence[StockItemInput], batches: Sequence[StockBatchInput], as_of: date
) -> dict[str, tuple[Fraction | None, str]]:
    """Purchase price per unit: average of good batches with stock, else the last received batch, else none."""
    out: dict[str, tuple[Fraction | None, str]] = {}
    for it in items:
        mine = [b for b in batches if b.item_id == it.id]
        good = [b for b in mine if b.qty > 0 and (b.expires_on is None or b.expires_on >= as_of)]
        if good:
            total = sum((Fraction(b.qty) for b in good), Fraction(0))
            weighted = sum((Fraction(b.qty) * b.unit_cost for b in good), Fraction(0))
            out[it.id] = (weighted / total, "average")
        elif mine:
            last = max(mine, key=lambda b: (b.received_on or date.min, b.id))
            out[it.id] = (Fraction(last.unit_cost), "last_batch")
        else:
            out[it.id] = (None, "none")
    return out


def _priced_lines(
    card: TechcardInput,
    items: dict[str, StockItemInput],
    prices: dict[str, tuple[Fraction | None, str]],
) -> list[PricedLine]:
    lines = []
    for ln in card.lines:
        it = items.get(ln.item_id)
        price = prices.get(ln.item_id, (None, "none"))[0]
        cost = 0 if price is None else div_round(*_ratio(Fraction(ln.qty) * price))
        lines.append(
            PricedLine(
                it.name if it else ln.item_id, it.unit if it else "", ln.qty, ln.part, price, cost
            )
        )
    return lines


def _ratio(value: Fraction) -> tuple[int, int]:
    return value.numerator, value.denominator


@dataclass(frozen=True)
class _Context:
    pnl: PnlMonthInput
    services_revenue: int
    hour_cost: int | None
    avg_minutes: int
    month: str
    settings: dict[str, ServiceSettingInput]
    cards: dict[str, TechcardInput]
    items: dict[str, StockItemInput]
    prices: dict[str, tuple[Fraction | None, str]]


def _price_figure(e: _Entry, price: int, rows: list[tuple[str, int]], net: int | None) -> Figure:
    manual = e.price_source == "manual"
    sources = {"manual"} if manual else {"vetmanager"}
    if net is None:
        label = "Цена, введённая вручную" if manual else "Средняя цена по счетам за 90 дней"
        note = "Разложить цену на части нельзя, пока нет техкарты: без материалов прибыль была бы завышена."
        return rub_figure(price, label, sources, note)
    lines = [item(label, amount) for label, amount in rows if amount]
    lines.append(item("Чистая прибыль", net))
    words = " + ".join(num(r.value) for r in lines[:-1] if isinstance(r.value, int))
    tail = f" − {num(-net)}" if net < 0 else f" + {num(net)}"
    return Figure(
        price, "rub", tuple(lines), ordered_sources(sources), f"{words}{tail} = {format_rub(price)}"
    )


def _list_price(e: _Entry) -> Figure:
    if e.price_source == "manual":
        return rub_figure(
            e.price, "Цена, введённая вручную", {"manual"}, "Продаж по услуге за 90 дней нет."
        )
    return rub_figure(
        e.price,
        "Средняя цена по счетам за 90 дней",
        {"vetmanager"},
        "Берём то, за сколько услугу продали, с учётом скидок.",
    )


def _build(e: _Entry, ctx: _Context) -> ServiceCost:
    st = ctx.settings.get(e.id)
    card = ctx.cards.get(e.id)
    pnl, price = ctx.pnl, e.price
    own_minutes = st is not None and st.minutes is not None
    minutes = st.minutes if st is not None and st.minutes is not None else ctx.avg_minutes
    missing: list[str] = []
    lines = _priced_lines(card, ctx.items, ctx.prices) if card else []
    if card is None:
        missing.append("recipe")
    if ctx.hour_cost is None:
        missing.append("hour_cost")
    if any(x.unit_price is None for x in lines):
        missing.append("item_no_cost")
    no_expenses = not pnl.fixed_lines and not pnl.obligation_lines  # a month without a statement
    if no_expenses:
        missing.append("no_expenses")
    amounts: dict[str, int | None] = {k: None for k in PART_KEYS}
    bp = st.doctor_pct_bp if st else None
    avg_pay = (
        div_round(price * pnl.doctor_percent_payouts, ctx.services_revenue)
        if ctx.services_revenue
        else 0
    )
    if bp is not None:
        amounts["doctor_pay"] = div_round(price * bp, BASIS_POINTS)
    elif not no_expenses:
        amounts["doctor_pay"] = avg_pay
    if not no_expenses:  # the empty P&L would put zeros here and show a false margin
        amounts["acquiring"] = (
            div_round(price * pnl.acquiring_fee, pnl.revenue) if pnl.revenue else 0
        )
        amounts["taxes"] = div_round(price * pnl.taxes, pnl.revenue) if pnl.revenue else 0
    if ctx.hour_cost is not None:
        amounts["fixed"] = div_round(ctx.hour_cost * minutes, MINUTES_IN_HOUR)
    if card is not None:
        for key in MATERIAL_PARTS:
            amounts[key] = sum(x.cost for x in lines if x.part == key)
    known = {k: a for k, a in amounts.items() if a is not None}
    net = None if card is None or no_expenses else price - sum(known.values())
    status = "no_recipe" if card is None else ("partial" if missing else "ok")
    parts, net_fig, margin_fig, monthly = _parts_and_profit(
        e, ctx, amounts, known, net, lines, minutes, own_minutes, bp
    )
    visits = count_figure(
        e.visits,
        f"Оказана за {month_word(ctx.month)}",
        {"vetmanager"},
        "Сумма количества по закрытым счетам за последний закрытый месяц.",
    )
    return ServiceCost(
        id=e.id, name=e.name, group=e.group, unit_label=UNIT_LABELS.get(e.id, "раз"), source=e.source,
        price_source=e.price_source, status=status, missing=tuple(missing), basis_month=ctx.month, minutes=minutes,
        minutes_source="own" if own_minutes else "clinic_average",
        price=_price_figure(e, price, [(PART_LABELS[k], a) for k, a in known.items()], net) if net is not None else _list_price(e),
        list_price=_list_price(e),
        net_profit=net_fig, net_margin_pct=margin_fig, margin_pct=margin_fig, parts=parts, visits_month=visits,
        monthly_profit=monthly, sort_margin=None if net is None else Fraction(net, price),
    )  # fmt: skip


def _parts_and_profit(
    e: _Entry, ctx: _Context, amounts: dict[str, int | None], known: dict[str, int], net: int | None,
    lines: list[PricedLine], minutes: int, own_minutes: bool, bp: int | None,
) -> tuple[tuple[PartRow, ...], Figure | None, Figure | None, Figure | None]:  # fmt: skip
    price = e.price
    shares: dict[str, Decimal] = {}
    margin = None
    if net is not None:
        order = [k for k in PART_KEYS if k in known]
        values = largest_remainder([known[k] for k in order] + [net], price)
        shares = dict(zip(order, values[:-1], strict=True))
        margin = values[-1]
    else:
        shares = {k: simple_share(a, price) for k, a in known.items()}
    figures: dict[str, Figure] = {}
    for key, amount in known.items():
        figures[key] = _part_figure(key, amount, e, ctx, lines, minutes, own_minutes, bp)
    parts = tuple(
        PartRow(k, PART_LABELS[k], figures.get(k), share_figure(known[k], price, shares[k]) if k in known else None)
        for k in PART_KEYS
    )  # fmt: skip
    if net is None or margin is None:
        return parts, None, None, None
    rows = (item("Цена", price), *(item(PART_LABELS[k], -a) for k, a in known.items() if a))
    note = "Столько остаётся с одной услуги после всех расходов и налогов."
    if net < 0:
        note = f"Услуга работает в минус: не хватает {format_rub(-net)} на одну услугу до нуля."
    net_fig = Figure(net, "rub", rows, ("calc",), note)
    margin_fig = Figure(
        margin,
        "pct",
        (item("Чистая прибыль", net), item("Цена", price)),
        ("calc",),
        f"{num(net)} ÷ {num(price)}",
    )
    monthly_value = net * e.visits
    monthly = rub_figure(
        monthly_value, "Чистая прибыль × оказана за месяц", {"calc"}, f"{num(net)} × {e.visits}",
        (item("Чистая прибыль одной услуги", net), item(f"Оказана за {month_word(ctx.month)}", e.visits, "count")),
    )  # fmt: skip
    return parts, net_fig, margin_fig, monthly


def _part_figure(
    key: str,
    amount: int,
    e: _Entry,
    ctx: _Context,
    lines: list[PricedLine],
    minutes: int,
    own_minutes: bool,
    bp: int | None,
) -> Figure:
    pnl = ctx.pnl
    if key == "doctor_pay":
        return doctor_pay_figure(
            amount, e.price, bp, pnl.doctor_percent_payouts, ctx.services_revenue
        )
    if key == "acquiring":
        return acquiring_figure(amount, e.price, pnl.acquiring_fee, pnl.revenue, ctx.month)
    if key == "taxes":
        return taxes_figure(amount, e.price, pnl.taxes, pnl.revenue, ctx.month)
    if key == "fixed":
        return fixed_figure(amount, ctx.hour_cost or 0, minutes, own_minutes)
    return material_figure(key, lines)


def _context(
    sales: Sequence[SaleInput], settings: Sequence[ServiceSettingInput], techcards: Sequence[TechcardInput],
    stock_items: Sequence[StockItemInput], stock_batches: Sequence[StockBatchInput], pnl_month: PnlMonthInput,
    hour_cost: int | Figure | None, avg_visit_minutes: int, month: str, as_of: date, services_revenue: int,
) -> _Context:  # fmt: skip
    cost = hour_cost.value if isinstance(hour_cost, Figure) else hour_cost
    return _Context(
        pnl_month, services_revenue, None if cost is None else int(cost), avg_visit_minutes, month,
        {s.service_id: s for s in settings}, {t.service_id: t for t in techcards}, {i.id: i for i in stock_items},
        _item_prices(stock_items, stock_batches, as_of),
    )  # fmt: skip


def _rows(
    sales: Sequence[SaleInput], manual_services: Sequence[ManualServiceInput], service_settings: Sequence[ServiceSettingInput],
    techcards: Sequence[TechcardInput], stock_items: Sequence[StockItemInput], stock_batches: Sequence[StockBatchInput],
    pnl_month: PnlMonthInput, hour_cost: int | Figure | None, avg_visit_minutes: int, month: str, as_of: date,
) -> list[ServiceCost]:  # fmt: skip
    settings = {s.service_id: s for s in service_settings}
    entries, services_revenue = _entries(sales, manual_services, settings, month, as_of)
    ctx = _context(sales, service_settings, techcards, stock_items, stock_batches, pnl_month, hour_cost,
                   avg_visit_minutes, month, as_of, services_revenue)  # fmt: skip
    return [_build(e, ctx) for e in entries]


def _sorted(rows: list[ServiceCost], sort: str, descending: bool) -> list[ServiceCost]:
    def key(r: ServiceCost) -> Fraction | None:
        if sort == "profit":
            return None if r.monthly_profit is None else Fraction(int(r.monthly_profit.value))
        return r.sort_margin

    rated = sorted((r for r in rows if key(r) is not None), key=lambda r: (key(r), r.name))
    rest = sorted((r for r in rows if key(r) is None), key=lambda r: r.name)
    return (rated[::-1] if descending else rated) + rest


def compute_price_list(
    sales: Sequence[SaleInput],
    manual_services: Sequence[ManualServiceInput],
    service_settings: Sequence[ServiceSettingInput],
    techcards: Sequence[TechcardInput],
    stock_items: Sequence[StockItemInput],
    stock_batches: Sequence[StockBatchInput],
    pnl_month: PnlMonthInput,
    hour_cost: int | Figure | None,
    avg_visit_minutes: int,
    month: str,
    as_of: date,
    sort: str = "margin",
    descending: bool = False,
) -> PriceList:
    """The list of services with price, margin and profit of the month; services without a margin go last."""
    rows = _rows(sales, manual_services, service_settings, techcards, stock_items, stock_batches, pnl_month,
                 hour_cost, avg_visit_minutes, month, as_of)  # fmt: skip
    ordered = _sorted(rows, sort, descending)
    by_margin = _sorted(rows, "margin", False)
    rated = [
        (r.name, Decimal(str(r.margin_pct.value))) for r in by_margin if r.margin_pct is not None
    ]
    counts = Counts(
        len(rows), sum(1 for r in rows if r.net_profit is not None and r.net_profit.value < 0),
        sum(1 for r in rows if r.status == "no_recipe"),
    )  # fmt: skip
    text = headline(rated, counts.all, counts.no_recipe)
    if rows and all("no_expenses" in r.missing for r in rows):
        text = (
            f"Нет данных о расходах за {month_word(month)}: прибыль услуг не считаем. "
            "Загрузите выписку банка."
        )
    return PriceList(month, text, counts, tuple(ordered))


def compute_service_cost(
    sales: Sequence[SaleInput],
    manual_services: Sequence[ManualServiceInput],
    service_settings: Sequence[ServiceSettingInput],
    techcards: Sequence[TechcardInput],
    stock_items: Sequence[StockItemInput],
    stock_batches: Sequence[StockBatchInput],
    pnl_month: PnlMonthInput,
    hour_cost: int | Figure | None,
    avg_visit_minutes: int,
    month: str,
    as_of: date,
    service_id: str,
) -> ServiceCost | None:
    """The card of one service; None if the service is not in the price list."""
    rows = _rows(sales, manual_services, service_settings, techcards, stock_items, stock_batches, pnl_month,
                 hour_cost, avg_visit_minutes, month, as_of)  # fmt: skip
    return next((r for r in rows if r.id == service_id), None)


def item_unit_costs(
    items: Sequence[StockItemInput], batches: Sequence[StockBatchInput], as_of: date
) -> dict[str, Figure | None]:
    """The purchase price of a unit of every stock item as a Figure (None: no price), rounded to the kopeck."""
    out: dict[str, Figure | None] = {}
    for it, (cost, basis) in _item_prices(items, batches, as_of).items():
        stock = next(i for i in items if i.id == it)
        if cost is None:
            out[it] = None
            continue
        value = div_round(cost.numerator, cost.denominator)
        exact = ""
        if cost.denominator != 1:
            exact = (
                f" Точная цена {unit_price_text(cost)} за {stock.unit}, в расчёте услуг берём её."
            )
        if basis == "last_batch":
            last = max(
                (b for b in batches if b.item_id == it),
                key=lambda b: (b.received_on or date.min, b.id),
            )
            when = f" от {format_date(last.received_on)}" if last.received_on else ""
            note = f"Остаток исчерпан или просрочен: берём цену последней партии{when}.{exact}"
            out[it] = rub_figure(value, "Цена последней партии", {"vetmanager"}, note)
        else:
            note = (
                "Средняя закупочная цена партий с остатком, срок годности которых не вышел." + exact
            )
            out[it] = rub_figure(value, "Средняя закупочная цена по остатку", {"vetmanager"}, note)
    return out


def recipe_defaults(
    sales: Sequence[SaleInput], pnl_month: PnlMonthInput, month: str, avg_visit_minutes: int
) -> tuple[Figure, Figure | None]:
    """What an empty field of the techcard form stands for: the average visit length and the clinic-average percent."""
    revenue = sum(
        ln.amount
        for sale in sales
        if sale.status == SALE_EXEC and sale.date.strftime("%Y-%m") == month
        for ln in sale.lines
        if ln.kind == LINE_SERVICE
    )
    minutes = count_figure(
        avg_visit_minutes,
        "Средняя длительность приёма клиники",
        {"manual"},
        "Настройка клиники, по умолчанию 30 минут.",
    )
    payouts = pnl_month.doctor_percent_payouts
    if revenue == 0 or payouts == 0:
        return minutes, None
    pct = Figure(
        pct_one_decimal(payouts, revenue), "pct",
        (item(f"Проценты врачам за {month_word(month)}", payouts), item(f"Выручка услуг за {month_word(month)}", revenue)),
        ordered_sources({"bank", "vetmanager", "calc"}), f"{num(payouts)} ÷ {num(revenue)}",
    )  # fmt: skip
    return minutes, pct
