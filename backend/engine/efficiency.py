"""Efficiency of the clinic (functions 33, 34): load of rooms or doctors, hour cost, what a busy hour brings.

Pure functions, rules E1-E6 of tests/golden/set06/README.md. Hours are whole after rounding half up; the load is the
ratio of the sums of hours (not the average of percents); the hour cost is one number for the whole clinic.
"""

import calendar
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction

from engine.dashboard_inputs import SaleInput, VisitInput
from engine.efficiency_inputs import DoctorInput, RoomBookingInput, RoomInput
from engine.figure import Figure, FigureItem
from engine.money import div_round, format_pct, format_rub, pct_one_decimal
from engine.pricing_figures import num
from engine.pricing_inputs import LINE_KIND_MATERIALS, PnlMonthInput
from engine.ru import MONTHS_NOMINATIVE, MONTHS_PREPOSITIONAL, plural

MINUTES_IN_HOUR = 60
DAYS_IN_WEEK = 7
LOAD_NOTE = "Считаем часы, а не среднее по кабинетам: большой кабинет весит больше."
HOUR_COST_NOTE = (
    "Постоянные без расходных материалов и обязательства, разделённые на рабочие часы клиники. "
    "Свободные часы остаются в расходах клиники: на цену услуг они не ложатся."
)


@dataclass(frozen=True)
class RoomLoad:
    id: str
    name: str
    load_pct: Figure
    busy_hours: Figure
    available_hours: Figure
    free_hours: Figure


@dataclass(frozen=True)
class DoctorLoad:
    id: str
    name: str
    visits: Figure
    load_pct: Figure | None
    busy_hours: Figure | None
    available_hours: Figure | None
    free_hours: Figure | None


@dataclass(frozen=True)
class HourPart:
    key: str  # hours | busy_hours | fixed | obligations
    label: str
    figure: Figure


@dataclass(frozen=True)
class Efficiency:
    month: str
    status: str  # ok | partial | empty
    partial_reasons: tuple[str, ...]
    headline: str | None
    load_by: str  # rooms | doctors
    visits: Figure
    avg_check: Figure | None
    load_pct: Figure | None
    busy_hours: Figure
    available_hours: Figure
    free_hours: Figure | None
    rooms: tuple[RoomLoad, ...]
    doctors: tuple[DoctorLoad, ...]
    hour_cost: Figure | None
    hour_margin: Figure | None
    hour_cost_parts: tuple[HourPart, ...]


def _item(label: str, value: int | Decimal, unit: str = "rub") -> FigureItem:
    return FigureItem(label, value, unit)


def _count(value: int, label: str, sources: tuple[str, ...], note: str) -> Figure:
    return Figure(value, "count", (_item(label, value, "count"),), sources, note)


def _hours(value: Fraction) -> int:
    """Whole hours, half up, from a number of minutes divided by 60 (a Fraction of hours is accepted)."""
    return div_round(value.numerator, value.denominator)


def _schedule_minutes(room: RoomInput, year: int, month: int) -> int:
    per_weekday = [0] * DAYS_IN_WEEK
    for slot in room.schedule or ():
        per_weekday[slot.weekday] += max(slot.to_min - slot.from_min, 0)
    days = calendar.monthrange(year, month)[1]
    return sum(per_weekday[date(year, month, d).weekday()] for d in range(1, days + 1))


def _in_month(day: date, month: str) -> bool:
    return day.strftime("%Y-%m") == month


def _load(busy: int, avail: int, note: str, sources: tuple[str, ...], free: int) -> Figure:
    rows = (_item("Занято, ч", busy, "count"), _item("Доступно, ч", avail, "count"))
    return Figure(
        pct_one_decimal(busy, avail), "pct", rows, sources, note,
        details=(_item("Свободно, ч", free, "count"),),
    )  # fmt: skip


def _hour_figures(
    busy: int, avail: int, where: str, sources: tuple[str, ...]
) -> tuple[Figure, Figure, Figure]:
    free = avail - busy
    note = "Округление до целого часа."
    free_fig = Figure(
        free, "count", (_item("Свободно, ч", free, "count"),), ("calc",), "Доступно минус занято.",
        details=(_item("Доступно, ч", avail, "count"), _item("Занято, ч", busy, "count")),
    )  # fmt: skip
    return (
        _count(busy, f"Занято в {where}", sources, note),
        _count(avail, f"Доступно в {where}", sources, note),
        free_fig,
    )


def _rooms_mode(
    rooms: Sequence[RoomInput], bookings: Sequence[RoomBookingInput], month: str
) -> bool:
    has_bookings = any(_in_month(b.date, month) for b in bookings)
    return bool(rooms) and all(r.schedule is not None for r in rooms) and has_bookings


def _room_rows(
    rooms: Sequence[RoomInput], bookings: Sequence[RoomBookingInput], month: str
) -> list[tuple[RoomInput, int, int]]:
    year, mon = int(month[:4]), int(month[5:])
    rows = []
    for room in sorted(rooms, key=lambda r: (r.name, r.id)):
        avail = _hours(Fraction(_schedule_minutes(room, year, mon), MINUTES_IN_HOUR))
        used = sum(b.minutes for b in bookings if b.room_id == room.id and _in_month(b.date, month))
        rows.append((room, _hours(Fraction(used, MINUTES_IN_HOUR)), avail))
    return rows


def _doctor_rows(
    doctors: Sequence[DoctorInput], visits: Sequence[VisitInput], month: str, avg_minutes: int
) -> list[tuple[DoctorInput, int, int, int | None]]:
    """(doctor, visits, busy hours, available hours or None)."""
    days = calendar.monthrange(int(month[:4]), int(month[5:]))[1]
    rows = []
    for doc in sorted(doctors, key=lambda d: (d.name, d.id)):
        count = sum(1 for v in visits if v.doctor_id == doc.id and _in_month(v.date, month))
        busy = _hours(Fraction(count * avg_minutes, MINUTES_IN_HOUR))
        avail = None
        if doc.hours_per_week is not None:
            avail = _hours(Fraction(doc.hours_per_week) * days / DAYS_IN_WEEK)
        rows.append((doc, count, busy, avail))
    return rows


def _hours_word(n: int) -> str:
    return f"{n} {plural(n, 'час', 'часа', 'часов')}"


def _headline(e_status: str, reasons: tuple[str, ...], load_by: str, load: Decimal | None, busy: int,
              avail: int, hour_cost: int | None, month: str) -> str | None:  # fmt: skip
    if e_status == "empty":
        return None
    if "no_doctor_hours" in reasons or load is None:
        return "Загрузку и стоимость часа пока посчитать нельзя: не указаны часы приёма врачей."
    head = f"Клиника загружена на {format_pct(load)}%"
    if hour_cost is None:
        name = MONTHS_NOMINATIVE[int(month[5:]) - 1]
        return f"{head}: свободно {_hours_word(avail - busy)}. Стоимость часа посчитать нельзя: нет данных банка за {name}."
    if load_by == "rooms":
        return f"{head}: свободно {_hours_word(avail - busy)}, час работы стоит {format_rub(hour_cost)}."
    return f"{head}: врачи принимали {busy} из {_hours_word(avail)}, час приёма стоит {format_rub(hour_cost)}."


def _visits_figure(
    visits: Sequence[VisitInput], month: str, doctors: Sequence[DoctorInput]
) -> Figure:
    names = {d.id: d.name for d in doctors}
    counts: dict[str, int] = {}
    nobody = 0
    for v in visits:
        if not _in_month(v.date, month):
            continue
        if v.doctor_id is None:
            nobody += 1
        else:
            counts[v.doctor_id] = counts.get(v.doctor_id, 0) + 1
    rows = [
        _item(names.get(k, k), n, "count")
        for k, n in sorted(counts.items(), key=lambda kv: names.get(kv[0], kv[0]))
    ]
    if nobody:
        rows.append(_item("Без врача", nobody, "count"))
    total = sum(counts.values()) + nobody
    if not rows:
        rows = [_item("Нет приёмов", 0, "count")]
    return Figure(total, "count", tuple(rows), ("vetmanager",), "Приёмы по дате визита за месяц.")


def _fixed_lines(pnl: PnlMonthInput) -> tuple[int, int]:
    fixed = sum(x.amount for x in pnl.fixed_lines if x.kind != LINE_KIND_MATERIALS)
    materials = sum(x.amount for x in pnl.fixed_lines if x.kind == LINE_KIND_MATERIALS)
    return fixed, materials


def compute_efficiency(
    visits: Sequence[VisitInput],
    sales: Sequence[SaleInput],
    doctors: Sequence[DoctorInput],
    rooms: Sequence[RoomInput],
    room_bookings: Sequence[RoomBookingInput],
    pnl_month: PnlMonthInput,
    avg_visit_minutes: int,
    month: str,
    as_of: date,
) -> Efficiency:
    """Load, hour cost and margin of a busy hour for `month` (a closed month)."""
    by_rooms = _rooms_mode(rooms, room_bookings, month)
    visits_fig = _visits_figure(visits, month, doctors)
    sums = _sum_hours(by_rooms, rooms, room_bookings, doctors, visits, month, avg_visit_minutes)
    room_out, doctor_out, busy, avail, parts_rows = sums
    reasons: list[str] = []
    if avail == 0 and not by_rooms:
        reasons.append("no_doctor_hours")
    fixed, materials = _fixed_lines(pnl_month)
    obligations = sum(x.amount for x in pnl_month.obligation_lines)
    if not pnl_month.fixed_lines and not pnl_month.obligation_lines:
        reasons.append("no_expenses")
    sources = ("vetmanager", "calc") if by_rooms else ("vetmanager", "manual", "calc")
    load_fig = None
    if avail > 0:
        load_fig = _load(
            busy,
            avail,
            f"{busy} ÷ {avail}. {LOAD_NOTE}{_unlisted_note(doctors, by_rooms)}",
            sources,
            avail - busy,
        )
    cost = _hour_cost(fixed, obligations, avail, reasons)
    margin = _hour_margin(pnl_month.marginal_profit, busy, cost)
    status = (
        "empty"
        if visits_fig.value == 0 and pnl_month.revenue == 0
        else ("partial" if reasons else "ok")
    )
    load_value = pct_one_decimal(busy, avail) if avail > 0 else None
    cost_value = None if cost is None else int(cost.value)
    return Efficiency(
        month=month, status=status, partial_reasons=tuple(reasons),
        headline=_headline(status, tuple(reasons), "rooms" if by_rooms else "doctors", load_value, busy, avail, cost_value, month),
        load_by="rooms" if by_rooms else "doctors", visits=visits_fig,
        avg_check=_avg_check(pnl_month.revenue, int(visits_fig.value)),
        load_pct=load_fig, busy_hours=_count(busy, "Занято, ч", sources, "Сумма занятых часов."),
        available_hours=_count(avail, "Доступно, ч", sources, "Сумма доступных часов."),
        free_hours=None if avail == 0 else _count(avail - busy, "Свободно, ч", ("calc",), "Доступно минус занято."),
        rooms=room_out, doctors=doctor_out, hour_cost=cost, hour_margin=margin,
        hour_cost_parts=_cost_parts(cost, by_rooms, parts_rows, busy, avail, fixed, materials, obligations, pnl_month),
    )  # fmt: skip


def _unlisted_note(doctors: Sequence[DoctorInput], by_rooms: bool) -> str:
    skipped = sum(1 for d in doctors if d.hours_per_week is None)
    if by_rooms or skipped == 0 or skipped == len(doctors):
        return ""
    return f" Врачей без указанных часов: {skipped}. Они в расчёт не вошли."


def _sum_hours(
    by_rooms: bool,
    rooms: Sequence[RoomInput],
    bookings: Sequence[RoomBookingInput],
    doctors: Sequence[DoctorInput],
    visits: Sequence[VisitInput],
    month: str,
    avg_minutes: int,
) -> tuple[tuple[RoomLoad, ...], tuple[DoctorLoad, ...], int, int, list[tuple[str, int, int]]]:
    where = _where(month)
    if by_rooms:
        rows = _room_rows(rooms, bookings, month)
        out = []
        for room, busy, avail in rows:
            src2 = ("vetmanager", "calc")
            b, a, f = _hour_figures(busy, avail, where, ("vetmanager",))
            out.append(
                RoomLoad(
                    room.id,
                    room.name,
                    _load(busy, avail, f"{busy} ÷ {avail}", src2, avail - busy),
                    b,
                    a,
                    f,
                )
            )
        room_parts = [(r.name, busy, avail) for r, busy, avail in rows]
        return (
            tuple(out),
            (),
            sum(p[1] for p in room_parts),
            sum(p[2] for p in room_parts),
            room_parts,
        )
    doc_rows = _doctor_rows(doctors, visits, month, avg_minutes)
    drows: list[DoctorLoad] = []
    parts: list[tuple[str, int, int]] = []
    for doc, count, doc_busy, d_avail in doc_rows:
        visits_fig = _count(
            count, "Приёмов за месяц", ("vetmanager",), "Приёмы по дате визита за месяц."
        )
        busy_fig = _count(
            doc_busy,
            f"Занято в {where}",
            ("vetmanager", "calc"),
            f"{count} приёмов × {avg_minutes} мин, до часа.",
        )
        if d_avail is None:
            drows.append(DoctorLoad(doc.id, doc.name, visits_fig, None, busy_fig, None, None))
            continue
        src3 = ("vetmanager", "manual", "calc")
        note = f"{count} приёмов × {avg_minutes} мин = {doc_busy} ч. Доступно: часы в неделю × дней в месяце ÷ 7 = {d_avail} ч."
        b, a, f = _hour_figures(doc_busy, d_avail, where, src3)
        drows.append(
            DoctorLoad(
                doc.id,
                doc.name,
                visits_fig,
                _load(doc_busy, d_avail, note, src3, d_avail - doc_busy),
                b,
                a,
                f,
            )
        )
        parts.append((doc.name, doc_busy, d_avail))
    return (), tuple(drows), sum(p[1] for p in parts), sum(p[2] for p in parts), parts


def _where(month: str) -> str:
    return MONTHS_PREPOSITIONAL[int(month[5:]) - 1]


def _hour_cost(fixed: int, obligations: int, avail: int, reasons: list[str]) -> Figure | None:
    if avail == 0 or "no_expenses" in reasons:
        return None
    total = fixed + obligations
    value = div_round(total, avail)
    first = div_round(fixed, avail)
    rows = (_item("Постоянные расходы", first), _item("Обязательства и амортизация", value - first))
    rub = num(total)
    return Figure(value, "rub", rows, ("calc",), f"{rub} ÷ {avail}. {HOUR_COST_NOTE}")


def _hour_margin(marginal: int, busy: int, cost: Figure | None) -> Figure | None:
    if cost is None or busy == 0:
        return None
    value = div_round(marginal, busy)
    rub = num(marginal)
    return Figure(
        value, "rub", (_item("Маржинальная прибыль на занятый час", value),), ("calc",),
        f"{rub} ÷ {busy}. После лекарств, процентов врачам и комиссий, до постоянных расходов и налогов.",
        details=(_item("Маржинальная прибыль", marginal), _item("Занятых часов", busy, "count")),
    )  # fmt: skip


def _avg_check(revenue: int, visits: int) -> Figure | None:
    if visits == 0:
        return None
    value = div_round(revenue, visits)
    rub = num(revenue)
    return Figure(
        value, "rub", (_item("Средний чек", value),), ("vetmanager",), f"{rub} ÷ {visits}. Выручка по закрытым счетам.",
        details=(_item("Выручка за месяц", revenue), _item("Приёмов", visits, "count")),
    )  # fmt: skip


def _cost_parts(
    cost: Figure | None, by_rooms: bool, rows: list[tuple[str, int, int]], busy: int, avail: int,
    fixed: int, materials: int, obligations: int, pnl: PnlMonthInput,
) -> tuple[HourPart, ...]:  # fmt: skip
    if cost is None:
        return ()
    src = ("vetmanager", "calc") if by_rooms else ("vetmanager", "manual", "calc")
    hours = Figure(avail, "count", tuple(_item(n, a, "count") for n, _, a in rows), src,
                   "Часы работы кабинетов по расписанию за месяц." if by_rooms else "Часы приёма врачей, которые указал владелец.")  # fmt: skip
    busy_fig = Figure(
        busy,
        "count",
        tuple(_item(n, b, "count") for n, b, _ in rows),
        src,
        "Длительность приёмов за месяц, до часа.",
    )
    lines = [x for x in pnl.fixed_lines if x.kind != LINE_KIND_MATERIALS]
    note = f"Постоянные расходы за месяц {format_rub(fixed + materials)} без расходных материалов {format_rub(materials)}: они уже в техкартах услуг."
    fixed_fig = Figure(fixed, "rub", tuple(_item(x.name, x.amount) for x in lines), ("bank",), note)
    obl = Figure(
        obligations, "rub", tuple(_item(x.name, x.amount) for x in pnl.obligation_lines), ("manual", "calc"),
        "Начисления обязательств за месяц: проценты, лизинг и амортизация.",
    )  # fmt: skip
    first = "Рабочих часов в месяц" if by_rooms else "Часов приёма в месяц"
    return (
        HourPart("hours", first, hours), HourPart("busy_hours", "Занято", busy_fig),
        HourPart("fixed", "Постоянные расходы", fixed_fig), HourPart("obligations", "Обязательства и амортизация", obl),
    )  # fmt: skip
