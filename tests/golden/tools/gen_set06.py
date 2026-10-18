"""Generates tests/golden/set06/data.json deterministically (fixed LCG, no randomness).

Set 06: one invented clinic G «Ясень», stage 5 "Прайс и себестоимость" (functions 11, 12, 33, 34). as_of = 2026-10-01: the last
closed month is September 2026 (it is the basis month), the price of a service is the average over the 90 days before as_of
(2026-07-03 .. 2026-09-30). Data: Vetmanager sales/visits since June, a stock with batches, doctors (weekly hours for the fallback
mode), rooms with a weekly schedule and bookings, service settings (minutes, doctor percent), techcards, and the month's totals of
the P&L (the figures that engine/pnl.py of stage 3 produces; here they are inputs).
What is DESIGNED here (tables below): units sold per month, prices (one price change, discounts), techcards, batches (averages with
fractions, a half-kopeck case, an expired batch, an exhausted item, an item without any batch), schedules, P&L totals.
Expected numbers are NOT computed here: see compute_expected_set06.py (reads only data.json).
Run: python tests/golden/tools/gen_set06.py
"""
import json
import pathlib
from datetime import date, timedelta

OUT = pathlib.Path(__file__).resolve().parent.parent / "set06" / "data.json"
CID = "S6"
AS_OF = date(2026, 10, 1)
MONTH = "2026-09"
PRICE_FROM, PRICE_TO = date(2026, 7, 3), date(2026, 9, 30)
PRICE_CHANGE = date(2026, 9, 15)           # vaccination: 1 200 -> 1 300 rubles from this day
DISCOUNT_PCT = 10                          # some ultrasound invoices in September

_state = 20261017


def rnd(lo, hi):
    global _state
    _state = (_state * 1103515245 + 12345) % (2**31)
    return lo + (_state >> 8) % (hi - lo + 1)


def slots(weekdays, start_min, end_min):
    return [{"weekday": w, "from_min": start_min, "to_min": end_min} for w in weekdays]


# ---------------------------------------------------------------- DESIGN: doctors (hours per week for the fallback mode)
DOCTORS = [
    {"id": "D1", "code": "D1", "name": "Иванова А.", "hours_per_week": "36", "days": [0, 1, 2, 3, 4]},
    {"id": "D2", "code": "D2", "name": "Петров В.", "hours_per_week": "37.5", "days": [0, 1, 2, 3, 4, 5]},
    {"id": "D3", "code": "D3", "name": "Сидорова Н.", "hours_per_week": "24", "days": [1, 3, 5]},
]
AVG_VISIT_MINUTES = 30

# ---------------------------------------------------------------- DESIGN: rooms (weekly schedule)
ROOMS = [
    {"id": "R1", "name": "Кабинет терапии", "schedule": slots(range(0, 5), 600, 1080) + slots([5], 600, 840)},   # 11 520 min = 192 h
    {"id": "R2", "name": "Операционная", "schedule": slots(range(0, 5), 600, 975)},                             # 8 250 min = 137,5 h
    {"id": "R3", "name": "Стационар", "schedule": slots(range(0, 7), 480, 1200)},                               # 21 600 min = 360 h
]

# ---------------------------------------------------------------- DESIGN: month totals of the P&L (kopecks); revenue is filled from the sales
PNL_FIXED = [
    {"name": "Оклады сотрудников", "amount": 13_700_000, "kind": "payroll"},
    {"name": "Аренда и коммуналка", "amount": 8_500_000, "kind": "rent"},
    {"name": "Маркетинг", "amount": 2_600_000, "kind": "marketing"},
    {"name": "Связь и прочее", "amount": 3_700_000, "kind": "other"},
    {"name": "Расходные материалы", "amount": 9_100_000, "kind": "materials"},   # already in the techcards: not in the hour cost
]
PNL_OBLIGATIONS = [
    {"name": "Амортизация оборудования", "amount": 1_520_000},
    {"name": "Лизинг (платёж целиком)", "amount": 1_200_000},
    {"name": "Проценты по кредиту", "amount": 620_000},
]
PNL_VARIABLE_TOTAL = 25_400_000
PNL_DOCTOR_PERCENT = 12_700_000        # percents paid to doctors in the month (the clinic average percent is this / service revenue)
PNL_ACQUIRING = 950_000
PNL_TAXES = 2_100_000

# ---------------------------------------------------------------- DESIGN: stock (qty is a decimal string: numeric(14,3) in the DB)
STOCK_ITEMS = [
    ("i01", "Перчатки смотровые", "пара"), ("i02", "Шприц 5 мл", "шт"), ("i03", "Вакцина комплексная", "доза"),
    ("i04", "Гель для УЗИ", "мл"), ("i05", "Золетил 100", "мл"), ("i06", "Ксилазин 2%", "мл"),
    ("i07", "Антибиотик инъекционный", "мл"), ("i08", "Шовный материал", "шт"), ("i09", "Пелёнка стерильная", "шт"),
    ("i10", "Система для капельницы", "шт"), ("i11", "Раствор Рингера 400 мл", "флакон"),
    ("i12", "Корм диетический, порция", "порц"), ("i13", "Салфетки антисептические", "шт"), ("i14", "Пропофол", "мл"),
    ("i15", "Лидокаин 2%", "мл"), ("i16", "Насадка эндоскопа одноразовая", "шт"),
]
BATCHES = [  # item, qty, unit_cost (kopecks per unit), received_on, expires_on
    ("i01", "60", 2_800, "2026-08-10", "2028-01-01"), ("i01", "40", 3_100, "2026-09-12", "2028-01-01"),
    ("i02", "200", 450, "2026-07-20", "2029-01-01"),
    ("i03", "30", 38_000, "2026-08-20", "2027-03-01"), ("i03", "20", 41_000, "2026-09-18", "2027-06-01"),
    ("i04", "500", 12, "2026-06-01", "2028-01-01"), ("i04", "300", 13, "2026-09-02", "2028-01-01"),
    ("i05", "10", 90_001, "2026-08-05", "2027-05-01"),
    ("i05", "5", 10, "2026-03-01", "2026-08-31"),                       # expired: not used (its price would distort the average)
    ("i06", "20", 25_300, "2026-07-14", "2027-02-01"),
    ("i07", "100", 4_800, "2026-08-01", "2027-08-01"), ("i07", "50", 5_100, "2026-09-10", "2027-09-01"),
    ("i08", "25", 21_500, "2026-08-15", "2029-01-01"),
    ("i09", "80", 7_800, "2026-08-12", "2028-01-01"),
    ("i10", "40", 5_900, "2026-08-12", "2029-01-01"),
    ("i11", "24", 7_450, "2026-08-18", "2027-02-01"), ("i11", "6", 7_900, "2026-09-25", "2026-10-01"),   # expires on as_of: still usable
    ("i12", "100", 11_000, "2026-09-05", "2027-01-01"),
    ("i13", "300", 150, "2026-08-02", "2028-01-01"),
    ("i14", "0", 61_000, "2026-07-05", "2026-12-01"), ("i14", "0", 64_500, "2026-08-20", "2027-01-01"),     # exhausted: last received
    ("i15", "50", 1_950, "2026-07-30", "2027-07-01"),
    # i16: no batch at all: no purchase price (item_no_cost)
]

# ---------------------------------------------------------------- DESIGN: services
# id: (name, group, minutes, doctor_pct_bp, list price, sold units Jul (from the 3rd), Aug, Sep, doctor id weights)
SERVICES = {
    "S1": ("Первичный приём терапевта", "Терапия", 30, 3000, 180_000, 66, 70, 80, [("D2", 7), ("D3", 3)]),
    "S2": ("Вакцинация комплексная", "Терапия", 15, None, 120_000, 40, 45, 50, [("D2", 5), ("D3", 3), ("D1", 2)]),
    "S3": ("УЗИ брюшной полости", "Диагностика", 30, 3000, 210_000, 25, 28, 30, [("D2", 1)]),
    "S4": ("Кастрация кота", "Хирургия", 60, 3000, 450_000, 14, 16, 18, [("D1", 1)]),
    "S5": ("Стоматология под наркозом", "Хирургия", 120, 3500, 980_000, 4, 5, 6, [("D1", 1)]),
    "S6": ("Стационар, сутки", "Стационар", 180, 2000, 240_000, 0, 0, 0, [("D2", 1)]),            # units come from STAYS
    "S7": ("Чистка ушей", "Терапия", 15, None, 60_000, 10, 12, 16, [("D2", 3), ("D3", 1)]),       # no techcard
    "S8": ("Рентген грудной клетки", "Диагностика", 20, 2500, 190_000, 4, 0, 0, [("D1", 1)]),      # sold in July only
    "S10": ("Выдача справки", None, None, None, 30_000, 18, 20, 25, [("D2", 1)]),                 # no settings, no techcard
    "S11": ("Осмотр без материалов", "Терапия", 20, 3000, 150_000, 8, 9, 10, [("D2", 1)]),         # an empty techcard (recorded)
}
STAYS = {"jul": [2, 3, 1, 2], "aug": [2, 3, 1, 2, 2], "sep": [3, 2, 1, 2, 1, 3]}               # nights per invoice
OUTSIDE_WINDOW = [  # (date, service, qty, unit price): before 2026-07-03, must not change the average price
    ("2026-06-20", "S8", 2, 170_000), ("2026-07-02", "S8", 1, 100_000), ("2026-06-25", "S12", 3, 100_000),
]
SERVICE_NAMES_EXTRA = {"S12": "Дегельминтизация разовая"}
SETTINGS = [  # service_id, name, group, minutes, doctor_pct_bp (S10 is absent; S12 never sold in the window; S9 never sold)
    ("S1", "Первичный приём терапевта", "Терапия", 30, 3000), ("S2", "Вакцинация комплексная", "Терапия", 15, None),
    ("S3", "УЗИ брюшной полости", "Диагностика", 30, 3000), ("S4", "Кастрация кота", "Хирургия", 60, 3000),
    ("S5", "Стоматология под наркозом", "Хирургия", 120, 3500), ("S6", "Стационар, сутки", "Стационар", 180, 2000),
    ("S7", "Чистка ушей", "Терапия", 15, None), ("S8", "Рентген грудной клетки", "Диагностика", 20, 2500),
    ("S9", "Пункция сустава", "Хирургия", 45, 3000), ("S11", "Осмотр без материалов", "Терапия", 20, 3000),
]
BOOKING_ROOM = {"S1": "R1", "S2": "R1", "S3": "R1", "S4": "R2", "S5": "R2", "S6": "R3", "S7": "R1", "S8": "R2", "S11": "R1"}
TECHCARDS = {  # service -> [(item, qty, part)]; S11 has a recorded empty techcard, S7 and S10 have none
    "S1": [("i01", "1", "supplies"), ("i13", "3", "supplies"), ("i02", "1", "supplies")],
    "S2": [("i03", "1", "drugs"), ("i02", "1", "supplies")],
    "S3": [("i04", "20", "supplies"), ("i13", "2", "supplies")],
    "S4": [("i05", "0.5", "anesthesia"), ("i06", "0.3", "anesthesia"), ("i07", "4", "drugs"), ("i15", "2", "drugs"),
           ("i08", "2", "supplies"), ("i09", "3", "supplies"), ("i01", "2", "supplies"), ("i13", "4", "supplies")],
    "S5": [("i14", "3", "anesthesia"), ("i15", "5", "drugs"), ("i07", "6", "drugs"), ("i09", "4", "supplies"),
           ("i01", "2", "supplies"), ("i13", "6", "supplies"), ("i16", "1", "supplies")],
    "S6": [("i10", "1", "supplies"), ("i11", "2", "drugs"), ("i12", "3", "supplies")],
    "S8": [("i13", "2", "supplies"), ("i01", "1", "supplies")],
    "S9": [("i08", "1", "supplies"), ("i15", "3", "drugs")],
    "S11": [],
    "M1": [],                      # manual service without sales: recorded empty techcard
}
# manual services (name + entered price). M1 has no sales; M2 matches the sales lines of S7 by the normalized name
# (trim, collapse spaces, case, ё = е) and is absorbed: S7 stays a Vetmanager service (designer: «совпавшая становится услугой из Ветменеджера»).
MANUAL_SERVICES = [{"id": "M1", "name": "Консультация ортопеда", "price": 250_000},
                   {"id": "M2", "name": "  Чистка  Ушей ", "price": 70_000}]
MANUAL_SETTINGS = [("M1", "Консультация ортопеда", "Ортопедия", 40, 3000)]
GOODS = [("Корм Royal Canin Renal 2 кг", 185_000), ("Шампунь лечебный", 62_000), ("Витамины для кошек", 98_000)]
DRAFTS_SEP = [("S1", 3), ("S3", 3), ("S4", 2)]    # status "save": not sold, not counted
DISCOUNTED_S3_SEP = 6                              # invoices with a 10% discount (amount < price x qty)
EXTRA_VISITS = 6                                   # visits per month without an invoice
NO_DOCTOR_VISITS_SEP = 5                           # September visits without a doctor
GOODS_SALES = 15                                   # per month, no doctor, no visit

CASES = [
    {"key": "main", "description": "все кабинеты с расписанием, приёмы привязаны к кабинетам: режим кабинетов",
     "drop_room_schedules": [], "drop_doctor_hours": []},
    {"key": "ward_no_schedule", "description": "у стационара нет расписания: запасной режим по часам приёма врачей",
     "drop_room_schedules": ["R3"], "drop_doctor_hours": []},
    {"key": "doctor_no_hours", "description": "запасной режим, у врача D3 не заданы часы приёма",
     "drop_room_schedules": ["R3"], "drop_doctor_hours": ["D3"]},
    {"key": "no_hours", "description": "нет ни расписания кабинетов, ни часов приёма врачей",
     "drop_room_schedules": ["R1", "R2", "R3"], "drop_doctor_hours": ["D1", "D2", "D3"]},
    {"key": "no_expenses", "description": "месяц без выписки: в ОПиУ нет расходов, стоимость часа посчитать нельзя (только экран эффективности)",
     "drop_room_schedules": [], "drop_doctor_hours": [], "no_expenses": True, "efficiency_only": True},
]


def days_between(first, last):
    d = first
    while d <= last:
        yield d
        d += timedelta(days=1)


def working_days(doctor_id, first, last):
    weekdays = next(d["days"] for d in DOCTORS if d["id"] == doctor_id)
    return [d for d in days_between(first, last) if d.weekday() in weekdays]


def pick_doctor(weights):
    x = rnd(1, sum(w for _, w in weights))
    for doctor, w in weights:
        if x <= w:
            return doctor
        x -= w
    return weights[-1][0]


def list_price(service_id, d):
    if service_id == "S2" and d >= PRICE_CHANGE:
        return 130_000
    return SERVICES[service_id][4]


def build_sales(first, last, units_index, stays):
    """Sales (without ids) of one month: [(date, status, doctor, [(kind, service, name, qty, unit price, amount)])]."""
    sales = []
    for sid, spec in SERVICES.items():
        name, weights = spec[0], spec[8]
        if sid == "S6":
            for qty in stays:
                d = first + timedelta(days=rnd(0, (last - first).days))
                sales.append((d, "exec", "D2", [("service", sid, name, qty, list_price(sid, d), qty * list_price(sid, d))]))
            continue
        discounted = DISCOUNTED_S3_SEP if (sid == "S3" and units_index == 7) else 0
        for k in range(spec[units_index]):
            doctor = pick_doctor(weights)
            days = [d for d in working_days(doctor, first, last) if d >= PRICE_FROM] if units_index == 5 else \
                working_days(doctor, first, last)
            d = days[rnd(0, len(days) - 1)]
            price = list_price(sid, d)
            amount = price - price * DISCOUNT_PCT // 100 if k < discounted else price
            sales.append((d, "exec", doctor, [("service", sid, name, 1, price, amount)]))
    if units_index == 7:
        for sid, count in DRAFTS_SEP:
            for _ in range(count):
                doctor = SERVICES[sid][8][0][0]
                days = working_days(doctor, first, last)
                d = days[rnd(0, len(days) - 1)]
                price = list_price(sid, d)
                sales.append((d, "save", doctor, [("service", sid, SERVICES[sid][0], 1, price, price)]))
    for _ in range(GOODS_SALES):
        name, price = GOODS[rnd(0, len(GOODS) - 1)]
        qty = rnd(1, 3)
        d = first + timedelta(days=rnd(0, (last - first).days))
        sales.append((d, "exec", None, [("good", None, name, qty, price, qty * price)]))
    return sales


def main():
    all_sales = build_sales(date(2026, 7, 1), date(2026, 7, 31), 5, STAYS["jul"]) \
        + build_sales(date(2026, 8, 1), date(2026, 8, 31), 6, STAYS["aug"]) \
        + build_sales(date(2026, 9, 1), date(2026, 9, 30), 7, STAYS["sep"])
    for d, sid, qty, price in OUTSIDE_WINDOW:
        name = SERVICES[sid][0] if sid in SERVICES else SERVICE_NAMES_EXTRA[sid]
        all_sales.append((date.fromisoformat(d), "exec", "D1", [("service", sid, name, qty, price, qty * price)]))
    all_sales.sort(key=lambda s: (s[0], s[1], s[2] or "", str(s[3])))
    sales, visits, bookings = [], [], []
    for i, (d, status, doctor, lines) in enumerate(all_sales, 1):
        rows = []
        for kind, sid, name, qty, price, amount in lines:
            row = {"kind": kind, "name": name, "qty": qty, "price": price, "amount": amount}
            if kind == "service":
                row["service_id"] = sid
                row["doctor_id"] = doctor
            rows.append(row)
        sales.append({"id": f"vm-inv-{i:04d}", "date": d.isoformat(), "status": status,
                      "amount": sum(r["amount"] for r in rows), "lines": rows})
        first = lines[0]
        if doctor and first[1] != "S6" and first[1] != "S12":
            visits.append({"date": d.isoformat(), "doctor_id": doctor})
        if first[0] == "service" and first[1] in BOOKING_ROOM and d >= date(2026, 8, 1):
            minutes = next(s[3] for s in SETTINGS if s[0] == first[1])
            bookings.append({"date": d.isoformat(), "room_id": BOOKING_ROOM[first[1]], "minutes": first[3] * minutes})
    for first_day, last_day in ((date(2026, 7, 1), date(2026, 7, 31)), (date(2026, 8, 1), date(2026, 8, 31)),
                                (date(2026, 9, 1), date(2026, 9, 30))):
        for _ in range(EXTRA_VISITS):
            doctor = DOCTORS[rnd(0, 2)]["id"]
            days = working_days(doctor, first_day, last_day)
            visits.append({"date": days[rnd(0, len(days) - 1)].isoformat(), "doctor_id": doctor})
    for _ in range(NO_DOCTOR_VISITS_SEP):
        visits.append({"date": date(2026, 9, 1 + rnd(0, 29)).isoformat(), "doctor_id": None})
    visits.sort(key=lambda v: (v["date"], v["doctor_id"] or ""))
    for i, v in enumerate(visits, 1):
        v["id"] = f"vm-vis-{i:04d}"
    bookings.sort(key=lambda b: (b["date"], b["room_id"], b["minutes"]))

    revenue = sum(s["amount"] for s in sales if s["status"] == "exec" and s["date"].startswith(MONTH))
    data = {
        "set": "06", "as_of": AS_OF.isoformat(), "month": MONTH,
        "price_window": {"from": PRICE_FROM.isoformat(), "to": PRICE_TO.isoformat()},
        "clinic": {"id": CID, "name": "Ветклиника «Ясень» (набор G)", "timezone": "Europe/Moscow",
                   "avg_visit_minutes": AVG_VISIT_MINUTES},
        "pnl_month": {"month": MONTH, "revenue": revenue, "variable_total": PNL_VARIABLE_TOTAL,
                      "marginal_profit": revenue - PNL_VARIABLE_TOTAL, "doctor_percent_payouts": PNL_DOCTOR_PERCENT,
                      "acquiring_fee": PNL_ACQUIRING, "taxes": PNL_TAXES, "fixed_lines": PNL_FIXED,
                      "obligation_lines": PNL_OBLIGATIONS},
        "doctors": [{"id": d["id"], "code": d["code"], "name": d["name"], "hours_per_week": d["hours_per_week"]} for d in DOCTORS],
        "rooms": ROOMS, "room_bookings": bookings,
        "manual_services": MANUAL_SERVICES,
        "service_settings": [{"service_id": s, "name": n, "group": g, "minutes": m, "doctor_pct_bp": p}
                             for s, n, g, m, p in SETTINGS + MANUAL_SETTINGS],
        "stock_items": [{"id": i, "name": n, "unit": u} for i, n, u in STOCK_ITEMS],
        "stock_batches": [{"id": f"b{k:02d}", "item_id": i, "qty": q, "unit_cost": c, "received_on": r, "expires_on": e}
                          for k, (i, q, c, r, e) in enumerate(BATCHES, 1)],
        "techcards": [{"service_id": s, "lines": [{"item_id": i, "qty": q, "part": p} for i, q, p in lines]}
                      for s, lines in TECHCARDS.items()],
        "visits": visits, "sales": sales, "cases": CASES,
    }
    write(data)
    print(f"written {OUT} ({len(sales)} sales, {len(visits)} visits, {len(bookings)} bookings, revenue {revenue})")


def emit(obj, level=0):
    """JSON with one line per row of long lists of objects (keeps the file small and diffable)."""
    pad = " " * (level + 1)
    if isinstance(obj, dict):
        items = [f"{pad}{json.dumps(k, ensure_ascii=False)}: {emit(v, level + 1)}" for k, v in obj.items()]
        return "{\n" + ",\n".join(items) + "\n" + " " * level + "}"
    if isinstance(obj, list) and len(obj) > 6 and all(isinstance(x, dict) for x in obj):
        return "[\n" + ",\n".join(pad + json.dumps(x, ensure_ascii=False) for x in obj) + "\n" + " " * level + "]"
    return json.dumps(obj, ensure_ascii=False)


def write(data):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(emit(data) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
