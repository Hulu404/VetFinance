"""Price list, cost card, techcard and stock item examples of golden set 6 (stage 5)."""

from fractions import Fraction
from typing import Any

from pricing_examples_common import (
    DATA,
    DAYS_UNIT,
    EXPECTED,
    MONTH_LABEL,
    PART_KEYS,
    PART_LABELS,
    PNL,
    count_fig,
    figure,
    fraction,
    item,
    money,
    num,
    pct,
    pct_of,
    qty_text,
    rub_fig,
    sid,
    unit_price_text,
)

from engine.money import div_round
from engine.ru import format_date, plural

STOCK = {i["id"]: i for i in DATA["stock_items"]}
COSTS = EXPECTED["item_costs"]
SETTINGS = {s["service_id"]: s for s in DATA["service_settings"]}
TECHCARDS = {t["service_id"]: t for t in DATA["techcards"]}
ACQ = "Комиссия клиники за сентябрь"
RECIPE_NOTE = (
    "Количество из техкарты × закупочная цена со склада. "
    "Если на складе несколько партий, берём среднюю по остатку."
)
PART_NOTES = {
    "drugs": RECIPE_NOTE,
    "anesthesia": "Берём средний расход из техкарты. Вес животного не учитывается.",
    "supplies": RECIPE_NOTE,
}


def unit_cost_fig(item_id: str) -> dict[str, Any] | None:
    info = COSTS[item_id]
    cost = fraction(info["unit_cost"])
    if cost is None:
        return None
    value = div_round(cost.numerator, cost.denominator)
    unit = STOCK[item_id]["unit"]
    exact = (
        f" Точная цена {unit_price_text(cost)} за {unit}, в расчёте услуг берём её."
        if cost.denominator != 1
        else ""
    )
    if info["basis"] == "last_batch":
        batches = [b for b in DATA["stock_batches"] if b["item_id"] == item_id]
        last = max(batches, key=lambda b: (b["received_on"], b["id"]))
        from datetime import date

        when = format_date(date.fromisoformat(last["received_on"]))
        return rub_fig(
            value,
            "Цена последней партии",
            ["vetmanager"],
            f"Остаток исчерпан: берём цену последней партии от {when}.{exact}",
        )
    note = "Средняя закупочная цена партий с остатком, срок годности которых не вышел." + exact
    return rub_fig(value, "Средняя закупочная цена по остатку", ["vetmanager"], note)


def line_label(line: dict[str, Any]) -> str:
    st = STOCK[line["item_id"]]
    price = unit_price_text(fraction(COSTS[line["item_id"]]["unit_cost"]) or Fraction(0))
    return f"{st['name']}, {qty_text(line['qty'])} {st['unit']} × {price}"


def part_fig(key: str, s: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any] | None:
    amount = s["parts"][key]
    if amount is None:
        return None
    price = s["price"]
    if key == "doctor_pay":
        return _doctor_pay(s, amount)
    if key in PART_NOTES:
        lines = [x for x in s["techcard_lines"] if x["part"] == key]
        rows = [item(line_label(x), x["cost"]) for x in lines if not x["no_cost"]]
        miss = [
            item(f"Нет цены закупки: {STOCK[x['item_id']]['name']}", 0)
            for x in lines
            if x["no_cost"]
        ]
        return figure(amount, "rub", rows, ["manual", "vetmanager"], PART_NOTES[key], miss or None)
    if key == "acquiring":
        share = pct_of(PNL["acquiring_fee"], PNL["revenue"])
        note = (
            f"{num(price)} × {pct(share)}%. Средняя комиссия клиники: {num(PNL['acquiring_fee'])} ÷ "
            f"{num(PNL['revenue'])} за сентябрь. Не зависит от того, чем заплатил клиент."
        )
        return rub_fig(amount, "Комиссия", ["bank", "calc"], note, [item(ACQ, share, "pct")])
    if key == "fixed":
        hour = ctx["hour_cost"]
        minutes = s["minutes"]
        det = [item("Стоимость часа", hour), item("Время услуги, мин", minutes, "count")]
        extra = ""
        if s["minutes_source"] == "clinic_average":
            extra = f" Длительность средняя по клинике: {minutes} мин. Укажите свою, чтобы расчёт был точнее."
        note = (
            f"{num(hour)} × {minutes} ÷ 60. Аренда, оклады, коммуналка и платежи по обязательствам, разделённые на "
            f"часы работы клиники. Свободные часы на цену услуг не ложатся.{extra}"
        )
        return rub_fig(amount, "Время в кабинете", ["manual", "calc"], note, det)
    share = pct_of(PNL["taxes"], PNL["revenue"])
    note = (
        f"{num(price)} × {num(PNL['taxes'])} ÷ {num(PNL['revenue'])}. Берём долю из отчёта «Прибыль и убытки» "
        "за последний закрытый месяц."
    )
    return rub_fig(
        amount,
        "Налоги и взносы",
        ["bank", "vetmanager", "calc"],
        note,
        [item("Доля налогов в выручке за сентябрь", share, "pct")],
    )


def _doctor_pay(s: dict[str, Any], amount: int) -> dict[str, Any]:
    own = SETTINGS.get(s["id"], {}).get("doctor_pct_bp")
    price = s["price"]
    if own is not None:
        share = own / 100
        note = f"{num(price)} × {pct(share)}%. Процент задан для этой услуги."
        return rub_fig(
            amount,
            "Процент врачу от цены",
            ["manual", "calc"],
            note,
            [item("Процент", share, "pct")],
        )
    revenue = services_revenue()
    share = pct_of(PNL["doctor_percent_payouts"], revenue)
    note = (
        f"Процент не задан: берём средний по клинике, {pct(share)}% (проценты врачам "
        f"{num(PNL['doctor_percent_payouts'])} ÷ выручка услуг {num(revenue)}). Оклады врачей уже в стоимости часа."
    )
    return rub_fig(
        amount,
        "Процент врачу от цены",
        ["bank", "vetmanager", "calc"],
        note,
        [item("Процент", share, "pct")],
    )


def services_revenue() -> int:
    return sum(
        ln["amount"]
        for sale in DATA["sales"]
        if sale["status"] == "exec" and sale["date"].startswith("2026-09")
        for ln in sale["lines"]
        if ln["kind"] == "service"
    )


def share_fig(amount: int, price: int, value: float) -> dict[str, Any]:
    return figure(
        value,
        "pct",
        [item("Сумма части", amount), item("Цена", price)],
        ["calc"],
        f"{num(amount)} ÷ {num(price)}",
    )


def price_fig(s: dict[str, Any], known: dict[str, int]) -> dict[str, Any]:
    price = s["price"]
    manual = s["price_basis"] == "manual"
    if s["net_profit"] is None:
        label = "Цена, введённая вручную" if manual else "Средняя цена по счетам за 90 дней"
        note = "Разложить цену на части нельзя, пока нет техкарты: без материалов прибыль была бы завышена."
        return rub_fig(price, label, ["manual" if manual else "vetmanager"], note)
    rows = [item(PART_LABELS[k], v) for k, v in known.items() if v]
    rows.append(item("Чистая прибыль", s["net_profit"]))
    signs = " + ".join(num(r["value"]) for r in rows[:-1]) + (
        f" − {num(-s['net_profit'])}" if s["net_profit"] < 0 else f" + {num(s['net_profit'])}"
    )
    return figure(
        price, "rub", rows, ["manual" if manual else "vetmanager"], f"{signs} = {money(price)}"
    )


def profit_figs(s: dict[str, Any], known: dict[str, int]) -> tuple[Any, Any, Any]:
    if s["net_profit"] is None:
        return None, None, None
    price, np_ = s["price"], s["net_profit"]
    rows = [item("Цена", price)] + [item(PART_LABELS[k], -v) for k, v in known.items() if v]
    note = "Столько остаётся с одной услуги после всех расходов и налогов."
    if np_ < 0:
        note = f"Услуга работает в минус: не хватает {money(-np_)} на одну услугу до нуля."
    net = figure(np_, "rub", rows, ["calc"], note)
    margin = figure(
        s["net_margin_pct"],
        "pct",
        [item("Чистая прибыль", np_), item("Цена", price)],
        ["calc"],
        f"{num(np_)} ÷ {num(price)}",
    )
    monthly = rub_fig(
        s["monthly_profit"],
        "Чистая прибыль × оказана за месяц",
        ["calc"],
        f"{num(np_)} × {s['visits_month']}",
        [
            item("Чистая прибыль одной услуги", np_),
            item("Оказана за сентябрь", s["visits_month"], "count"),
        ],
    )
    return net, margin, monthly


def visits_fig(s: dict[str, Any]) -> dict[str, Any]:
    return count_fig(
        s["visits_month"],
        f"Оказана за {MONTH_LABEL[:-5]} 2026",
        ["vetmanager"],
        "Сумма количества по закрытым счетам за последний закрытый месяц.",
    )


def list_price(s: dict[str, Any]) -> dict[str, Any]:
    if s["price_basis"] == "manual":
        return rub_fig(
            s["price"], "Цена, введённая вручную", ["manual"], "Продаж по услуге за 90 дней нет."
        )
    return rub_fig(
        s["price"],
        "Средняя цена по счетам за 90 дней",
        ["vetmanager"],
        "Берём то, за сколько услугу продали, с учётом скидок.",
    )


def list_item(s: dict[str, Any]) -> dict[str, Any]:
    known = {k: s["parts"][k] for k in PART_KEYS if s["parts"][k] is not None}
    _, margin, monthly = profit_figs(s, known)
    return {
        "id": sid(s["id"]),
        "name": s["name"],
        "group": s["group"],
        "unit_label": DAYS_UNIT.get(s["id"], "раз"),
        "source": s["source"],
        "price": list_price(s),
        "visits_month": visits_fig(s),
        "margin_pct": margin,
        "monthly_profit": monthly,
        "status": s["status"],
    }


def card(s: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    known = {k: s["parts"][k] for k in PART_KEYS if s["parts"][k] is not None}
    net, margin, monthly = profit_figs(s, known)
    shares = s["shares"] or {}
    parts = []
    for key in PART_KEYS:
        amount = s["parts"][key]
        if key in ("drugs", "anesthesia", "supplies") and s["status"] == "no_recipe":
            amount = None
        fig = part_fig(key, s, ctx) if amount is not None else None
        share = shares.get(key, pct_of(amount, s["price"]) if amount is not None else None)
        parts.append(
            {
                "key": key,
                "label": PART_LABELS[key],
                "amount": fig,
                "share_pct": share_fig(amount, s["price"], share) if amount is not None else None,
            }
        )
    return {
        "service": {
            "id": sid(s["id"]),
            "name": s["name"],
            "group": s["group"],
            "unit_label": DAYS_UNIT.get(s["id"], "раз"),
            "source": s["source"],
            "price_source": s["price_basis"],
        },
        "status": s["status"],
        "missing": s["missing"],
        "basis_month": "2026-09",
        "minutes": s["minutes"],
        "minutes_source": s["minutes_source"],
        "price": price_fig(s, known),
        "net_profit": net,
        "net_margin_pct": margin,
        "parts": parts,
        "visits_month": visits_fig(s),
        "monthly_profit": monthly,
    }


def defaults() -> dict[str, Any]:
    revenue = services_revenue()
    avg = DATA["clinic"]["avg_visit_minutes"]
    doctor = figure(
        pct_of(PNL["doctor_percent_payouts"], revenue),
        "pct",
        [
            item("Проценты врачам за сентябрь", PNL["doctor_percent_payouts"]),
            item("Выручка услуг за сентябрь", revenue),
        ],
        ["bank", "vetmanager", "calc"],
        f"{num(PNL['doctor_percent_payouts'])} ÷ {num(revenue)}",
    )
    minutes = count_fig(
        avg,
        "Средняя длительность приёма клиники",
        ["manual"],
        "Настройка клиники, по умолчанию 30 минут.",
    )
    return {"minutes": minutes, "doctor_pct": doctor}


def recipe(s: dict[str, Any]) -> dict[str, Any]:
    tc = TECHCARDS.get(s["id"])
    st = SETTINGS.get(s["id"], {})
    bp = st.get("doctor_pct_bp")
    items = [
        {
            "item_id": sid(x["item_id"]),
            "name": STOCK[x["item_id"]]["name"],
            "unit": STOCK[x["item_id"]]["unit"],
            "group": x["part"],
            "qty": float(x["qty"]),
            "unit_cost": unit_cost_fig(x["item_id"]),
        }
        for x in (tc["lines"] if tc else [])
    ]
    return {
        "service": {"id": sid(s["id"]), "name": s["name"]},
        "has_recipe": tc is not None,
        "minutes": st.get("minutes"),
        "doctor_pct": None if bp is None else bp / 100,
        "items": items,
        "defaults": defaults(),
    }


def stock_items() -> dict[str, Any]:
    rows = [
        {
            "id": sid(i["id"]),
            "name": i["name"],
            "unit": i["unit"],
            "unit_cost": unit_cost_fig(i["id"]),
        }
        for i in DATA["stock_items"]
    ]
    return {"items": rows, "next_cursor": None}


def headline(items: list[dict[str, Any]], counts: dict[str, int]) -> str:
    rated = [x for x in items if x["margin_pct"] is not None]
    loss = [x for x in rated if x["margin_pct"]["value"] < 0]
    if not rated:
        return "Техкарт пока нет, поэтому маржу мы не считаем. Начните с самых частых услуг: для каждой нужен список материалов и время."
    if loss:
        n = len(loss)
        worst = loss[0]
        text = (
            f"{n} {plural(n, 'услуга', 'услуги', 'услуг')} из {counts['all']} "
            f"{plural(n, 'стоит', 'стоят', 'стоят')} клинике больше, чем {plural(n, 'приносит', 'приносят', 'приносят')}. "
            f"Сильнее всего «{worst['name']}»: {pct(worst['margin_pct']['value'])}%."
        )
    else:
        low = rated[0]
        text = f"Все услуги с техкартой приносят прибыль. Меньше всего у «{low['name']}»: {pct(low['margin_pct']['value'])}%."
    if counts["no_recipe"]:
        k = counts["no_recipe"]
        text += f" У {k} {plural(k, 'услуги', 'услуг', 'услуг')} нет техкарты, поэтому их маржу мы не считаем."
    return text
