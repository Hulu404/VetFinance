"""Efficiency examples of golden set 6: the five cases (rooms, fallback, a doctor without hours, no hours, no expenses)."""

from typing import Any

from pricing_examples_common import (
    DATA,
    EXPECTED,
    PNL,
    count_fig,
    figure,
    item,
    money,
    num,
    rub_fig,
    sid,
)

from engine.ru import plural

DOCTORS = {d["id"]: d for d in DATA["doctors"]}
VISITS_NOTE = "Приёмы по дате визита за сентябрь."


def hours_word(n: int) -> str:
    return f"{n} {plural(n, 'час', 'часа', 'часов')}"


def load_fig(eff: dict[str, Any], note: str, sources: list[str]) -> dict[str, Any]:
    rows = [
        item("Занято, ч", eff["busy_hours"], "count"),
        item("Доступно, ч", eff["available_hours"], "count"),
    ]
    return figure(eff["load_pct"], "pct", rows, sources, note)


def row_load(
    busy: int, avail: int, free: int, value: float, note: str, sources: list[str]
) -> dict[str, Any]:
    rows = [item("Занято, ч", busy, "count"), item("Доступно, ч", avail, "count")]
    return figure(value, "pct", rows, sources, note, [item("Свободно, ч", free, "count")])


def hours_figs(r: dict[str, Any], what: str, sources: list[str]) -> dict[str, Any]:
    avail = count_fig(
        r["available_hours"], f"Доступно в {what}", sources, "Округление до целого часа."
    )
    busy = count_fig(r["busy_hours"], f"Занято в {what}", sources, "Округление до целого часа.")
    free = figure(
        r["free_hours"],
        "count",
        [item("Свободно, ч", r["free_hours"], "count")],
        ["calc"],
        "Доступно минус занято.",
        [
            item("Доступно, ч", r["available_hours"], "count"),
            item("Занято, ч", r["busy_hours"], "count"),
        ],
    )
    return {"available_hours": avail, "busy_hours": busy, "free_hours": free}


def room_out(r: dict[str, Any]) -> dict[str, Any]:
    note = f"{r['busy_hours']} ÷ {r['available_hours']}"
    return {
        "id": sid(r["id"]),
        "name": r["name"],
        "load_pct": row_load(
            r["busy_hours"],
            r["available_hours"],
            r["free_hours"],
            r["load_pct"],
            note,
            ["vetmanager", "calc"],
        ),
        **hours_figs(r, "сентябре", ["vetmanager"]),
    }


def doctor_out(d: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": sid(d["id"]),
        "name": d["name"],
        "visits": count_fig(d["visits"], "Приёмов за сентябрь", ["vetmanager"], VISITS_NOTE),
        "load_pct": None,
        "busy_hours": None,
        "available_hours": None,
        "free_hours": None,
    }
    if d["available_hours"] is None:
        out["busy_hours"] = count_fig(
            d["busy_hours"],
            "Занято в сентябре",
            ["vetmanager", "calc"],
            "Приёмы × средняя длительность приёма.",
        )
        return out
    note = f"{d['visits']} приёмов × 30 мин = {d['busy_hours']} ч. Доступно: часы в неделю × 30 дней ÷ 7 = {d['available_hours']} ч."
    out["load_pct"] = row_load(
        d["busy_hours"],
        d["available_hours"],
        d["free_hours"],
        d["load_pct"],
        note,
        ["vetmanager", "manual", "calc"],
    )
    out.update(hours_figs(d, "сентябре", ["vetmanager", "manual", "calc"]))
    return out


def parts(eff: dict[str, Any]) -> list[dict[str, Any]]:
    by_room = eff["load_by"] == "rooms"
    rows = (
        eff["rooms"] if by_room else [d for d in eff["doctors"] if d["available_hours"] is not None]
    )
    src = ["vetmanager", "calc"] if by_room else ["vetmanager", "manual", "calc"]
    fixed = [x for x in PNL["fixed_lines"] if x["kind"] != "materials"]
    materials = sum(x["amount"] for x in PNL["fixed_lines"] if x["kind"] == "materials")
    hours = figure(
        eff["available_hours"],
        "count",
        [item(r["name"], r["available_hours"], "count") for r in rows],
        src,
        "Часы работы кабинетов по расписанию за месяц."
        if by_room
        else "Часы приёма врачей, которые указал владелец.",
    )
    busy = figure(
        eff["busy_hours"],
        "count",
        [item(r["name"], r["busy_hours"], "count") for r in rows],
        src,
        "Длительность приёмов за месяц, округление до часа.",
    )
    fixed_fig = figure(
        eff["pool"]["fixed"],
        "rub",
        [item(x["name"], x["amount"]) for x in fixed],
        ["bank"],
        f"Постоянные расходы за сентябрь {money(eff['pool']['fixed'] + materials)} без расходных материалов "
        f"{money(materials)}: они уже в техкартах услуг.",
    )
    obligations = figure(
        eff["pool"]["obligations"],
        "rub",
        [item(x["name"], x["amount"]) for x in PNL["obligation_lines"]],
        ["manual", "calc"],
        "Начисления обязательств за сентябрь: проценты, лизинг и амортизация.",
    )
    first = "Рабочих часов в месяц" if by_room else "Часов приёма в месяц"
    labelled = [
        ("hours", first, hours),
        ("busy_hours", "Занято", busy),
        ("fixed", "Постоянные расходы", fixed_fig),
        ("obligations", "Обязательства и амортизация", obligations),
    ]
    return [{"key": k, "label": label, "figure": f} for k, label, f in labelled]


def headline(eff: dict[str, Any]) -> str:
    if eff["status"] == "partial" and "no_doctor_hours" in eff["partial_reasons"]:
        return "Загрузку и стоимость часа пока посчитать нельзя: не указаны часы приёма врачей."
    load = f"Клиника загружена на {str(eff['load_pct']).replace('.', ',')}%"
    if eff["hour_cost"] is None:
        return f"{load}: свободно {hours_word(eff['free_hours'])}. Стоимость часа посчитать нельзя: нет данных банка за сентябрь."
    if eff["load_by"] == "rooms":
        return f"{load}: свободно {hours_word(eff['free_hours'])}, час работы стоит {money(eff['hour_cost'])}."
    return f"{load}: врачи принимали {eff['busy_hours']} из {hours_word(eff['available_hours'])}, час приёма стоит {money(eff['hour_cost'])}."


def efficiency(case: str) -> dict[str, Any]:
    eff = EXPECTED["cases"][case]["efficiency"]
    rooms_mode = eff["load_by"] == "rooms"
    rooms = [room_out(r) for r in eff["rooms"]] if rooms_mode else []
    doctors = [] if rooms_mode else [doctor_out(d) for d in eff["doctors"]]
    visits_rows = [item(DOCTORS[k]["name"], v, "count") for k, v in eff["visits_by_doctor"].items()]
    visits_rows.append(item("Без врача", eff["visits_without_doctor"], "count"))
    out: dict[str, Any] = {
        "month": "2026-09",
        "as_of": EXPECTED["as_of"],
        "data_as_of": "2026-10-01T04:12:00+03:00",
        "period": {
            "month": "2026-09",
            "status": "closed",
            "from": "2026-09-01",
            "to": None,
            "first_month": "2026-06",
        },
        "status": eff["status"],
        "partial_reasons": eff["partial_reasons"],
        "headline": headline(eff),
        "load_by": eff["load_by"],
        "visits": figure(eff["visits"], "count", visits_rows, ["vetmanager"], VISITS_NOTE),
        "load_pct": None,
        "avg_check": None,
        "rooms": rooms,
        "doctors": doctors,
        "hour_cost": None,
        "hour_margin": None,
        "hour_cost_parts": [],
    }
    if eff["load_pct"] is not None:
        note = f"{eff['busy_hours']} ÷ {eff['available_hours']}. Считаем часы, а не среднее по кабинетам: большой кабинет весит больше."
        if any(d["available_hours"] is None for d in doctors) and eff["status"] == "ok":
            n = sum(1 for d in doctors if d["available_hours"] is None)
            note += f" Врачей без указанных часов: {n}. Они в расчёт не вошли."
        src = ["vetmanager", "calc"] if rooms_mode else ["vetmanager", "manual", "calc"]
        out["load_pct"] = load_fig(eff, note, src)
    revenue = PNL["revenue"]
    out["avg_check"] = rub_fig(
        eff["avg_check"],
        "Средний чек",
        ["vetmanager"],
        f"{num(revenue)} ÷ {eff['visits']}. Выручка по закрытым счетам.",
        [item("Выручка за сентябрь", revenue), item("Приёмов", eff["visits"], "count")],
    )
    if eff["hour_cost"] is not None:
        lines = eff["hour_cost_lines"]
        note = (
            f"{num(eff['pool']['total'])} ÷ {eff['available_hours']}. Постоянные без расходных материалов и обязательства, "
            "разделённые на рабочие часы клиники. Свободные часы остаются в расходах клиники: на цену услуг они не ложатся."
        )
        out["hour_cost"] = figure(
            eff["hour_cost"],
            "rub",
            [
                item("Постоянные расходы", lines["fixed"]),
                item("Обязательства и амортизация", lines["obligations"]),
            ],
            ["calc"],
            note,
        )
        out["hour_margin"] = rub_fig(
            eff["hour_margin"],
            "Маржинальная прибыль на занятый час",
            ["calc"],
            f"{num(eff['marginal_profit'])} ÷ {eff['busy_hours']}. После лекарств, процентов врачам и комиссий, "
            "до постоянных расходов и налогов.",
            [
                item("Маржинальная прибыль", eff["marginal_profit"]),
                item("Занятых часов", eff["busy_hours"], "count"),
            ],
        )
        out["hour_cost_parts"] = parts(eff)
    return out


def settings() -> dict[str, Any]:
    return {
        "avg_visit_minutes": DATA["clinic"]["avg_visit_minutes"],
        "doctors": [
            {"id": sid(d["id"]), "name": d["name"], "hours_per_week": float(d["hours_per_week"])}
            for d in DATA["doctors"]
        ],
    }
