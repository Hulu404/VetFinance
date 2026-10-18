"""Figures and texts of the service cost (stage 5): the tooltips of every part of the price. Display only, no decisions."""

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction

from engine.figure import Figure, FigureItem, ordered_sources
from engine.money import NBSP, div_round, format_pct, format_rub, pct_one_decimal
from engine.ru import MONTHS_NOMINATIVE, plural

PART_KEYS = ("doctor_pay", "drugs", "anesthesia", "supplies", "acquiring", "fixed", "taxes")
PART_LABELS = {
    "doctor_pay": "ЗП врача",
    "drugs": "Препараты",
    "anesthesia": "Анестезия",
    "supplies": "Расходники",
    "acquiring": "Эквайринг",
    "fixed": "Постоянные",
    "taxes": "Налоги и взносы",
}
MATERIAL_NOTES = {
    "drugs": "Количество из техкарты × закупочная цена со склада. Если на складе несколько партий, берём среднюю по остатку.",
    "anesthesia": "Берём средний расход из техкарты. Вес животного не учитывается.",
    "supplies": "Количество из техкарты × закупочная цена со склада. Если на складе несколько партий, берём среднюю по остатку.",
}


@dataclass(frozen=True)
class PricedLine:
    name: str
    unit: str
    qty: Decimal
    part: str
    unit_price: Fraction | None  # kopecks per unit, exact; None: no purchase price
    cost: int  # kopecks, 0 without a price


def num(kopecks: int) -> str:
    """'1 168,06' without the rouble sign."""
    return format_rub(kopecks).replace(f"{NBSP}₽", "")


def pct(value: Decimal | float) -> str:
    return format_pct(Decimal(str(value)))


def item(label: str, value: int | Decimal, unit: str = "rub") -> FigureItem:
    return FigureItem(label, value, unit)


def rub_figure(
    value: int, label: str, sources: set[str], note: str, details: tuple[FigureItem, ...] = ()
) -> Figure:
    return Figure(
        value, "rub", (item(label, value),), ordered_sources(sources), note, details=details
    )


def count_figure(value: int, label: str, sources: set[str], note: str) -> Figure:
    return Figure(value, "count", (item(label, value, "count"),), ordered_sources(sources), note)


def month_word(month: str) -> str:
    return MONTHS_NOMINATIVE[int(month[5:]) - 1]


def qty_text(qty: Decimal) -> str:
    return format(qty.normalize(), "f").replace(".", ",")


def unit_price_text(cost: Fraction | None) -> str:
    if cost is None:
        return "—"
    rub = Decimal(cost.numerator) / Decimal(cost.denominator) / 100
    text = f"{rub:,.4f}".rstrip("0").rstrip(".").replace(",", NBSP).replace(".", ",")
    return f"{text}{NBSP}₽"


def line_label(line: PricedLine) -> str:
    return f"{line.name}, {qty_text(line.qty)} {line.unit} × {unit_price_text(line.unit_price)}"


def material_figure(key: str, lines: list[PricedLine]) -> Figure:
    mine = [x for x in lines if x.part == key]
    rows = tuple(item(line_label(x), x.cost) for x in mine if x.unit_price is not None)
    missing = tuple(item(f"Нет цены закупки: {x.name}", 0) for x in mine if x.unit_price is None)
    total = sum(x.cost for x in mine)
    return Figure(
        total,
        "rub",
        rows,
        ordered_sources({"manual", "vetmanager"}),
        MATERIAL_NOTES[key],
        details=missing,
    )


def doctor_pay_figure(
    amount: int, price: int, own_pct_bp: int | None, payouts: int, services_revenue: int
) -> Figure:
    if own_pct_bp is not None:
        share = Decimal(own_pct_bp) / 100
        note = f"{num(price)} × {pct(share)}%. Процент задан для этой услуги."
        return rub_figure(
            amount,
            "Процент врачу от цены",
            {"manual", "calc"},
            note,
            (FigureItem("Процент", share, "pct"),),
        )
    share = pct_one_decimal(payouts, services_revenue) if services_revenue else Decimal(0)
    note = (
        f"Процент не задан: берём средний по клинике, {pct(share)}% (проценты врачам {num(payouts)} ÷ "
        f"выручка услуг {num(services_revenue)}). Оклады врачей уже в стоимости часа."
    )
    return rub_figure(
        amount,
        "Процент врачу от цены",
        {"bank", "vetmanager", "calc"},
        note,
        (FigureItem("Процент", share, "pct"),),
    )


def acquiring_figure(amount: int, price: int, fee: int, revenue: int, month: str) -> Figure:
    share = pct_one_decimal(fee, revenue) if revenue else Decimal(0)
    note = (
        f"{num(price)} × {pct(share)}%. Средняя комиссия клиники: {num(fee)} ÷ {num(revenue)} за {month_word(month)}. "
        "Не зависит от того, чем заплатил клиент."
    )
    details = (FigureItem(f"Комиссия клиники за {month_word(month)}", share, "pct"),)
    return rub_figure(amount, "Комиссия", {"bank", "calc"}, note, details)


def taxes_figure(amount: int, price: int, taxes: int, revenue: int, month: str) -> Figure:
    share = pct_one_decimal(taxes, revenue) if revenue else Decimal(0)
    note = (
        f"{num(price)} × {num(taxes)} ÷ {num(revenue)}. Берём долю из отчёта «Прибыль и убытки» "
        "за последний закрытый месяц."
    )
    details = (FigureItem(f"Доля налогов в выручке за {month_word(month)}", share, "pct"),)
    return rub_figure(amount, "Налоги и взносы", {"bank", "vetmanager", "calc"}, note, details)


def fixed_figure(amount: int, hour_cost: int, minutes: int, own_minutes: bool) -> Figure:
    extra = (
        ""
        if own_minutes
        else f" Длительность средняя по клинике: {minutes} мин. Укажите свою, чтобы расчёт был точнее."
    )
    note = (
        f"{num(hour_cost)} × {minutes} ÷ 60. Аренда, оклады, коммуналка и платежи по обязательствам, разделённые "
        f"на часы работы клиники. Свободные часы на цену услуг не ложатся.{extra}"
    )
    details = (item("Стоимость часа", hour_cost), item("Время услуги, мин", minutes, "count"))
    return rub_figure(amount, "Время в кабинете", {"manual", "calc"}, note, details)


def share_figure(amount: int, price: int, value: Decimal) -> Figure:
    return Figure(
        value,
        "pct",
        (item("Сумма части", amount), item("Цена", price)),
        ("calc",),
        f"{num(amount)} ÷ {num(price)}",
    )


def largest_remainder(amounts: list[int], price: int) -> list[Decimal]:
    """Shares of the price in tenths of a percent that add up to exactly 100,0 (ties go to the earlier part)."""
    exact = [Fraction(a * 1000, price) for a in amounts]
    floors = [e.numerator // e.denominator for e in exact]
    spare = 1000 - sum(floors)
    order = sorted(range(len(amounts)), key=lambda i: (-(exact[i] - floors[i]), i))
    for i in order[:spare]:
        floors[i] += 1
    return [Decimal(f) / 10 for f in floors]


def simple_share(amount: int, price: int) -> Decimal:
    return Decimal(div_round(amount * 1000, price)) / 10


def headline(names_margins: list[tuple[str, Decimal]], total: int, no_recipe: int) -> str | None:
    """names_margins: rated services, worst margin first."""
    if total == 0:
        return None
    if not names_margins:
        return (
            "Техкарт пока нет, поэтому маржу мы не считаем. Начните с самых частых услуг: "
            "для каждой нужен список материалов и время."
        )
    loss = [x for x in names_margins if x[1] < 0]
    if loss:
        n = len(loss)
        text = (
            f"{n} {plural(n, 'услуга', 'услуги', 'услуг')} из {total} {plural(n, 'стоит', 'стоят', 'стоят')} клинике "
            f"больше, чем {plural(n, 'приносит', 'приносят', 'приносят')}. Сильнее всего «{loss[0][0]}»: {pct(loss[0][1])}%."
        )
    else:
        name, margin = names_margins[0]
        text = f"Все услуги с техкартой приносят прибыль. Меньше всего у «{name}»: {pct(margin)}%."
    if no_recipe:
        text += f" У {no_recipe} {plural(no_recipe, 'услуги', 'услуг', 'услуг')} нет техкарты, поэтому их маржу мы не считаем."
    return text
