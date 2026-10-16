"""Generates tests/golden/set04/data.json deterministically (fixed LCG, no randomness).

Set 04: one invented clinic, 3 doctors, 2026-07-01 .. 2026-09-30 (three full months), stage 3 "Отчёты":
P&L (function 14), norm (15), stock (17), services vs goods (18), export (20).
Monthly totals of every category are DESIGNED here (tables DESIGN_*), split into operations by a fixed LCG.
Expected numbers are NOT computed here: see compute_expected_set04.py (reads only data.json).
"""
import json
import pathlib
from datetime import date, timedelta

OUT = pathlib.Path(__file__).resolve().parent.parent / "set04" / "data.json"
CID = "S4"
MONTHS = ["2026-07", "2026-08", "2026-09"]
START, END = date(2026, 7, 1), date(2026, 9, 30)
RATE_BP = 190  # acquiring tariff, 1.9%

_state = 20261014


def rnd(lo, hi):
    global _state
    _state = (_state * 1103515245 + 12345) % (2**31)
    return lo + (_state >> 8) % (hi - lo + 1)


def div_round(n, d):
    sign = -1 if n < 0 else 1
    return sign * ((abs(n) * 2 + d) // (d * 2))


DOCTORS = [{"id": "D1", "name": "Ильина М."}, {"id": "D2", "name": "Петров А."}, {"id": "D3", "name": "Соколова Е."}]
ACCOUNTS = [
    {"id": "S4-bank", "clinic_id": CID, "name": "Расчётный счёт", "type": "bank", "opening_balance": 90_000_000, "opening_date": "2026-07-01"},
    {"id": "S4-cash", "clinic_id": CID, "name": "Касса", "type": "cash", "opening_balance": 1_200_000, "opening_date": "2026-07-01"},
]

# name, type, norm_key, direction, norm_min_pct, norm_max_pct (clinic override of the benchmark; None: use benchmark), payroll
# payroll: the article is salary of staff; inside "Постоянные расходы" such articles form the child row "ФОТ (оклады)"
CATEGORIES = [
    ("Выручка наличные", "income", None, None, None, None, False),
    ("Выручка эквайринг", "income", None, None, None, None, False),
    ("Проценты врачам", "variable", "payroll", "services", None, None, True),
    ("Препараты и расходники", "variable", "drugs", "goods", None, None, False),
    ("Корма для перепродажи", "variable", None, "goods", None, None, False),
    ("Лаборатории", "variable", "lab", "services", None, None, False),
    ("Оклады врачей", "fixed", "payroll", None, None, None, True),
    ("Оклады персонала", "fixed", None, None, None, None, True),
    ("Аренда", "fixed", "rent", None, None, None, False),
    ("Коммунальные и связь", "fixed", "rent", None, None, None, False),
    ("Реклама", "fixed", "marketing", None, 2.0, 6.0, False),  # clinic's own norm 2-6% instead of the industry 3-7%
    ("Прочие расходы", "fixed", None, None, None, None, False),
    ("Налоги и взносы", "tax", None, None, None, None, False),
    ("Платежи по кредитам и лизингу", "obligation", None, None, None, None, False),
    ("Покупка оборудования", "capex", None, None, None, None, False),
    ("Вывод средств владельца", "owner_draw", None, None, None, None, False),
]

# industry norms (starting values = prototype v7, an estimate of the product owner, see README)
BENCHMARKS = [
    {"key": "payroll", "label": "ФОТ врачей", "kind": "expense", "min_pct": 22.0, "max_pct": 28.0, "sort": 1},
    {"key": "drugs", "label": "Препараты и расходники", "kind": "expense", "min_pct": 20.0, "max_pct": 25.0, "sort": 2},
    {"key": "rent", "label": "Аренда и коммуналка", "kind": "expense", "min_pct": 5.0, "max_pct": 10.0, "sort": 3},
    {"key": "lab", "label": "Лаборатории", "kind": "expense", "min_pct": 3.0, "max_pct": 6.0, "sort": 4},
    {"key": "writeoff", "label": "Списание по сроку", "kind": "expense", "min_pct": 0.0, "max_pct": 0.8, "sort": 5},
    {"key": "acquiring", "label": "Эквайринг", "kind": "expense", "min_pct": 1.0, "max_pct": 2.0, "sort": 6},
    {"key": "marketing", "label": "Маркетинг", "kind": "expense", "min_pct": 3.0, "max_pct": 7.0, "sort": 7},
    {"key": "net_profit", "label": "Чистая прибыль", "kind": "profit", "min_pct": 12.0, "max_pct": 20.0, "sort": 8},
]
for b in BENCHMARKS:
    b["source"] = "prototype-v7 (оценка владельца продукта, не публикация)"

# ---------------------------------------------------------------- DESIGN: revenue (exec invoices), kopecks
DESIGN_REVENUE = {  # month: (services, goods)
    "2026-07": (59_924_035, 47_190_610),
    "2026-08": (63_257_520, 51_541_185),
    "2026-09": (64_132_070, 45_683_540),
}
INVOICES_PER_MONTH = {"2026-07": 142, "2026-08": 151, "2026-09": 147}  # exec invoices


def month_days(month):
    y, m = map(int, month.split("-"))
    d = date(y, m, 1)
    while d.month == m:
        yield d
        d += timedelta(days=1)


def spread(total, n):
    """n positive integer parts, deterministic pseudo-random, summing to total exactly."""
    w = [rnd(60, 140) for _ in range(n)]
    parts = [total * x // sum(w) for x in w]
    parts[-1] += total - sum(parts)
    return parts


def make_sales():
    sales, payments = [], []
    for month in MONTHS:
        days = list(month_days(month))
        n = INVOICES_PER_MONTH[month]
        # day of each exec invoice: weekdays get more
        weights = [1 if d.weekday() >= 5 else 2 for d in days]
        slots = []
        for _ in range(n):
            r, acc = rnd(0, sum(weights) - 1), 0
            for d, w in zip(days, weights):
                acc += w
                if r < acc:
                    slots.append(d)
                    break
        slots.sort()
        kinds = []  # per invoice: does it have a service line / a good line
        for _ in range(n):
            has_service = rnd(1, 10) <= 7
            has_good = (not has_service) or rnd(1, 10) <= 5
            kinds.append((has_service, has_good))
        # make sure the last invoice has both lines (receives rounding remainders)
        kinds[-1] = (True, True)
        svc_idx = [i for i, k in enumerate(kinds) if k[0]]
        good_idx = [i for i, k in enumerate(kinds) if k[1]]
        svc_total, good_total = DESIGN_REVENUE[month]
        svc_parts = dict(zip(svc_idx, spread(svc_total, len(svc_idx))))
        good_parts = dict(zip(good_idx, spread(good_total, len(good_idx))))
        for i, d in enumerate(slots):
            lines = []
            if i in svc_parts:
                lines.append({"kind": "service", "amount": svc_parts[i]})
            if i in good_parts:
                lines.append({"kind": "good", "amount": good_parts[i]})
            sales.append({"id": f"vm-inv-{len(sales) + 1:04d}", "date": d.isoformat(), "status": "exec",
                          "pay": "cash" if rnd(1, 10) <= 3 else "card", "doctor_id": DOCTORS[rnd(0, 2)]["id"],
                          "amount": sum(x["amount"] for x in lines), "lines": lines})
        # drafts (not revenue): about 3%
        for _ in range(max(2, n // 33)):
            d = days[rnd(0, len(days) - 1)]
            amt = rnd(80_000, 600_000)
            sales.append({"id": f"vm-inv-{len(sales) + 1:04d}", "date": d.isoformat(), "status": "save", "pay": "card",
                          "doctor_id": DOCTORS[rnd(0, 2)]["id"], "amount": amt, "lines": [{"kind": "service", "amount": amt}]})
    sales.sort(key=lambda s: (s["date"], s["id"]))
    for i, s in enumerate(sales, 1):  # ids follow the date order
        s["id"] = f"vm-inv-{i:04d}"
    for s in sales:
        if s["status"] == "exec":
            payments.append({"id": f"vm-pay-{len(payments) + 1:04d}", "invoice_id": s["id"], "date": s["date"],
                             "amount": s["amount"], "method": s["pay"]})
    return sales, payments


# ---------------------------------------------------------------- DESIGN: operations. (day, amount) lists in kopecks
# category -> month -> [(day, account, source, amount, description)]
def B(day, amount, desc, src="bank"):
    return (day, "bank", src, amount, desc)


def C(day, amount, desc):
    return (day, "cash", "manual", amount, desc)


DESIGN_EXPENSES = {
    "Препараты и расходники": {
        "2026-07": [B(3, 5_897_010, "ООО «Зоовет», закупка препаратов"), B(10, 6_120_000, "ООО «Вет-Снаб», закупка препаратов"),
                    B(17, 5_700_030, "ООО «Зоовет», закупка препаратов"), B(24, 5_871_000, "ООО «Вет-Снаб», закупка препаратов")],
        "2026-08": [B(4, 6_100_000, "ООО «Зоовет», закупка препаратов"), B(11, 7_016_095, "ООО «Вет-Снаб», закупка препаратов"),
                    B(19, 18_000_000, "ООО «Зоовет», закупка препаратов впрок, годовой объём со скидкой"),
                    B(26, 8_100_000, "ООО «Вет-Снаб», закупка препаратов")],
        "2026-09": [B(2, 6_000_000, "ООО «Зоовет», закупка препаратов"), B(9, 6_240_000, "ООО «Вет-Снаб», закупка препаратов"),
                    B(16, 6_160_000, "ООО «Зоовет», закупка препаратов"), B(23, 6_100_000, "ООО «Вет-Снаб», закупка препаратов")],
    },
    "Корма для перепродажи": {
        "2026-07": [B(8, 4_800_000, "ООО «Корм-Опт», оплата кормов"), B(22, 4_854_000, "ООО «Корм-Опт», оплата кормов")],
        "2026-08": [B(7, 5_000_000, "Оплата поставщику кормов (бот)", "bot"), B(21, 5_120_000, "ООО «Корм-Опт», оплата кормов")],
        "2026-09": [B(6, 4_000_000, "Оплата поставщику кормов (бот)", "bot"), B(20, 4_000_000, "ООО «Корм-Опт», оплата кормов")],
    },
    "Лаборатории": {
        "2026-07": [B(12, 2_200_000, "Лаборатория «Шанс Био», анализы"), B(26, 2_261_525, "Лаборатория «Шанс Био», анализы")],
        "2026-08": [B(14, 2_398_000, "Лаборатория «Шанс Био», анализы"), B(28, 2_400_000, "Лаборатория «Шанс Био», анализы")],
        "2026-09": [B(11, 2_600_000, "Лаборатория «Шанс Био», анализы"), B(25, 2_600_000, "Лаборатория «Шанс Био», анализы")],
    },
    "Проценты врачам": {
        "2026-07": [B(25, 15_200_000, "Проценты врачам за месяц")],
        "2026-08": [B(25, 15_900_000, "Проценты врачам за месяц")],
        "2026-09": [B(25, 17_000_000, "Проценты врачам за месяц")],
    },
    "Оклады врачей": {
        "2026-07": [B(10, 4_000_000, "Оклады врачей, аванс"), B(25, 4_700_000, "Оклады врачей, расчёт")],
        "2026-08": [B(10, 4_300_000, "Оклады врачей, аванс"), B(25, 4_700_000, "Оклады врачей, расчёт")],
        "2026-09": [B(10, 4_500_000, "Оклады врачей, аванс"), B(25, 4_800_000, "Оклады врачей, расчёт")],
    },
    "Оклады персонала": {
        "2026-07": [B(10, 2_300_000, "Оклады персонала, аванс"), B(25, 2_700_000, "Оклады персонала, расчёт")],
        "2026-08": [B(10, 2_500_000, "Оклады персонала, аванс"), B(25, 2_750_000, "Оклады персонала, расчёт")],
        "2026-09": [B(10, 2_600_000, "Оклады персонала, аванс"), B(25, 2_900_000, "Оклады персонала, расчёт")],
    },
    "Аренда": {m: [B(1, 8_500_000, "Аренда помещения")] for m in MONTHS},
    "Коммунальные и связь": {
        "2026-07": [B(15, 1_931_860, "Коммунальные услуги"), B(16, 500_000, "Связь и интернет")],
        "2026-08": [B(15, 2_010_475, "Коммунальные услуги"), B(16, 500_000, "Связь и интернет")],
        "2026-09": [B(15, 2_141_040, "Коммунальные услуги"), B(16, 500_000, "Связь и интернет")],
    },
    "Реклама": {
        "2026-07": [B(9, 3_800_000, "Реклама в соцсетях")],
        "2026-08": [B(8, 4_100_000, "Реклама в соцсетях")],
        "2026-09": [B(8, 2_310_000, "Реклама в соцсетях")],
    },
    "Прочие расходы": {
        "2026-07": [C(6, 311_000, "Хозрасходы из кассы"), C(20, 1_563_230, "Хозрасходы из кассы")],
        "2026-08": [C(5, 900_000, "Хозрасходы из кассы"), C(19, 1_203_000, "Хозрасходы из кассы")],
        "2026-09": [C(4, 510_015, "Хозрасходы из кассы"), C(18, 690_000, "Хозрасходы из кассы")],
    },
    "Налоги и взносы": {
        "2026-07": [B(18, 5_245_000, "Налоги и взносы")],
        "2026-08": [B(18, 5_532_000, "Налоги и взносы")],
        "2026-09": [B(18, 5_200_000, "Налоги и взносы")],
    },
    "Платежи по кредитам и лизингу": {
        m: [B(10, 2_650_000, "Кредит на аппарат УЗИ, платёж по графику"), B(10, 1_200_000, "Лизинг рентген-аппарата, платёж")]
        for m in MONTHS
    },
    "Покупка оборудования": {"2026-07": [B(14, 8_500_000, "Покупка центрифуги")]},
    "Вывод средств владельца": {"2026-08": [B(28, 15_000_000, "Вывод средств владельцем")]},
}

# obligations that produce the P&L line "Обязательства и амортизация" (module of stage 4; set 04 gives the charges)
LOAN_START, LOAN_RATE_BP, LOAN_PAYMENT = 62_000_000, 1400, 2_650_000
LEASE_MONTHLY = 1_200_000
EQUIPMENT = [  # id, name, cost, life in months, first month of amortization
    ("uzi", "Аппарат УЗИ", 67_200_000, 60, "2026-07"),
    ("xray", "Рентген-аппарат", 37_800_000, 60, "2026-07"),
    ("analyzer", "Анализатор крови", 23_450_000, 60, "2026-07"),
    ("centrifuge", "Центрифуга", 8_500_000, 36, "2026-08"),
]


def make_obligation_charges():
    charges, balance = [], LOAN_START
    for month in MONTHS:
        interest = div_round(balance * LOAN_RATE_BP, 12 * 10_000)
        charges.append({"month": month, "obligation_id": "loan-uzi", "name": "Кредит на аппарат УЗИ", "kind": "loan_interest",
                        "amount": interest, "basis": f"остаток долга на 1-е число {balance} коп. x {LOAN_RATE_BP} б.п. / 12"})
        balance -= LOAN_PAYMENT - interest
        charges.append({"month": month, "obligation_id": "lease-xray", "name": "Лизинг рентген-аппарата", "kind": "lease",
                        "amount": LEASE_MONTHLY, "basis": "платёж по договору целиком"})
        for oid, name, cost, life, first in EQUIPMENT:
            if month >= first:
                charges.append({"month": month, "obligation_id": f"am-{oid}", "name": f"Амортизация: {name}", "kind": "amortization",
                                "amount": div_round(cost, life), "basis": f"стоимость {cost} коп. / {life} мес."})
    return charges


# ---------------------------------------------------------------- transactions
def make_transactions(sales):
    txs = []

    def add(acc, d, desc, cat, src, kind, amount, status="ok", group=None):
        t = {"id": "", "clinic_id": CID, "account_id": f"{CID}-{acc}", "date": d.isoformat(), "description": desc,
             "category": cat, "source": src, "kind": kind, "amount": amount, "status": status}
        if group:
            t["transfer_group"] = group
        txs.append(t)

    # revenue money: cash on the day of the sale; card: net credit on the next business day (Fri-Sun -> Monday)
    by_day = {}
    for s in sales:
        if s["status"] == "exec":
            day = by_day.setdefault(s["date"], {"cash": 0, "card": 0})
            day[s["pay"]] += s["amount"]
    for ds in sorted(by_day):
        d = date.fromisoformat(ds)
        if by_day[ds]["cash"]:
            add("cash", d, "Оплата наличными за день", "Выручка наличные", "vetmanager", "in", by_day[ds]["cash"])
        card = by_day[ds]["card"]
        if card:
            credit_day = d + timedelta(days=1)
            while credit_day.weekday() >= 5:
                credit_day += timedelta(days=1)
            net = card - div_round(card * RATE_BP, 10_000)
            add("bank", credit_day, f"Эквайринг: зачисление за {d.strftime('%d.%m')}", "Выручка эквайринг", "bank", "in", net)
    for cat, per_month in DESIGN_EXPENSES.items():
        for month, ops in per_month.items():
            y, m = map(int, month.split("-"))
            for day, acc, src, amount, desc in ops:
                add(acc, date(y, m, day), desc, cat, src, "out", -amount)
    D = date
    # a payment entered by the bot and the same payment from the statement a day later: the statement copy is the duplicate
    add("bank", D(2026, 8, 8), "ООО «Корм-Опт», оплата кормов", "Корма для перепродажи", "bank", "out", -5_000_000, status="duplicate")
    add("bank", D(2026, 9, 7), "ООО «Корм-Опт», оплата кормов", "Корма для перепродажи", "bank", "out", -4_000_000, status="duplicate")
    # unrecognised operations: debits count in the P&L as "Без статьи", the credit is never revenue
    add("bank", D(2026, 8, 23), "Списание, назначение не распознано", None, "bank", "out", -213_050, status="check")
    add("bank", D(2026, 9, 21), "Списание, назначение не распознано", None, "bank", "out", -1_840_000, status="check")
    add("bank", D(2026, 8, 30), "Поступление, назначение не распознано", None, "bank", "in", 940_000, status="check")
    # cash collection to the bank (transfers between own accounts: two legs, not income and not expense)
    moves = [(D(2026, 7, 11), 10_000_000), (D(2026, 7, 27), 10_000_000), (D(2026, 8, 12), 15_000_000), (D(2026, 8, 29), 14_500_000),
             (D(2026, 9, 12), 14_500_000), (D(2026, 9, 28), 14_000_000)]
    for n, (d, amt) in enumerate(moves, 1):
        g = f"S4-trf-{n}"
        add("cash", d, "Перевод между счетами", None, "manual", "transfer", -amt, group=g)
        add("bank", d, "Перевод между счетами", None, "manual", "transfer", amt, group=g)
    txs.sort(key=lambda t: (t["date"], t["account_id"], t["amount"], t["description"]))
    for i, t in enumerate(txs, 1):
        t["id"] = f"{CID}-tx-{i:03d}"
    return txs


# ---------------------------------------------------------------- stock (function 17), snapshot at 2026-09-30
STOCK_AS_OF = date(2026, 9, 30)


def d_(offset):
    return (STOCK_AS_OF + timedelta(days=offset)).isoformat()


# id, name, days since last movement (idle), batches [(qty, unit_cost kop, days to expiry | None)]
STOCK = [
    ("g01", "Корм Royal Canin Renal 2 кг", 18, [(30, 185_000, 60)]),                      # expires exactly in 60 days: in
    ("g02", "Кетофен 10%, флакон", 3, [(8, 117_500, 24)]),
    ("g03", "Синулокс 250 мг, упаковка", 5, [(12, 71_650, 45)]),
    ("g04", "Вакцина Нобивак Rabies, доза", 1, [(9, 124_450, 59)]),
    ("g05", "Цефтриаксон, флакон", 1, [(25, 3_850, 76), (15, 3_700, -5)]),                # one batch is already expired
    ("g06", "Шприцы 5 мл, упаковка 100 шт", 10, [(60, 95_000, 520)]),
    ("g07", "Система для капельницы", 60, [(1200, 2_850, 270)]),                            # idle exactly 60: frozen
    ("g08", "Бинт эластичный", 59, [(200, 4_200, None)]),                                  # idle 59: not frozen
    ("g09", "Ошейник от блох", 90, [(120, 45_000, None)]),                                 # idle exactly 90
    ("g10", "Корм Hill's Prescription Diet 3 кг", 89, [(40, 289_000, 102)]),               # idle 89: bucket 60-89
    ("g11", "Лежак средний", 180, [(20, 112_000, None)]),                                  # idle exactly 180
    ("g12", "Рентген-плёнка 35x43", 199, [(10, 1_480_000, 62)]),                           # expires in 62 days: out
    ("g13", "Вакцина Эурикан, доза", 20, [(20, 97_500, 61)]),                              # expires in 61 days: out
    ("g14", "Мелоксикам 5 мг/мл, флакон", 2, [(5, 52_000, 1), (3, 52_000, 0)]),            # expires in 1 day and today: in
    ("g15", "Активированный уголь", 241, []),                                              # nothing on hand: not frozen
    ("g16", "Хлоргексидин 0,05%, флакон", 97, [(22, 18_500, 36)]),                         # frozen AND expiring
]
WRITEOFFS = [  # date, item, qty, amount, reason
    ("2026-07-09", "Вакцина Нобивак Rabies, доза", 3, 373_350, "expired"),
    ("2026-07-23", "Антисептик, флакон", 12, 266_650, "expired"),
    ("2026-07-30", "Пипетка стеклянная", 20, 90_000, "damaged"),
    ("2026-08-13", "Мазь ветеринарная, туба", 14, 530_000, "expired"),
    ("2026-08-27", "Корм Royal Canin Gastro 2 кг", 2, 360_000, "expired"),
    ("2026-09-03", "Кетофен 10%, флакон", 6, 705_000, "expired"),
    ("2026-09-17", "Вакцина Нобивак DHPPi, доза", 11, 1_368_950, "expired"),
    ("2026-09-26", "Цефтриаксон, флакон", 30, 111_000, "expired"),
    ("2026-09-26", "Капли глазные, флакон", 25, 805_050, "expired"),
    ("2026-09-12", "Стекло предметное, упаковка", 4, 420_000, "damaged"),
]


def make_stock():
    items, batches = [], []
    for iid, name, idle, bs in STOCK:
        items.append({"id": iid, "name": name, "last_movement": d_(-idle)})
        for qty, cost, left in bs:
            batches.append({"item_id": iid, "qty": qty, "unit_cost": cost, "expires_on": d_(left) if left is not None else None})
    consumption, d = [], START
    while d <= END:
        consumption.append({"date": d.isoformat(), "amount": rnd(800_000, 1_100_000) + rnd(0, 99)})
        d += timedelta(days=1)
    wo = [{"id": f"S4-wo-{i:02d}", "date": dt, "item": item, "qty": q, "amount": a, "reason": r}
          for i, (dt, item, q, a, r) in enumerate(sorted(WRITEOFFS), 1)]
    return {"as_of": STOCK_AS_OF.isoformat(), "items": items, "batches": batches, "writeoffs": wo, "consumption": consumption}


def main():
    sales, payments = make_sales()
    txs = make_transactions(sales)
    data = {
        "months": MONTHS,
        "clinic": {"id": CID, "name": "Ветеринарная клиника «Берёзка»", "timezone": "Europe/Moscow",
                   "acquiring_rate_bp": RATE_BP},
        "doctors": DOCTORS,
        "accounts": ACCOUNTS,
        "categories": [{"name": n, "type": t, "norm_key": k, "direction": dr, "norm_min_pct": lo, "norm_max_pct": hi, "payroll": pr}
                       for n, t, k, dr, lo, hi, pr in CATEGORIES],
        "benchmarks": BENCHMARKS,
        "bank_covered_to": "2026-09-30",  # last day covered by the loaded bank statements
        "transactions": txs,
        "sales": sales,
        "payments": payments,
        "obligation_charges": make_obligation_charges(),
        "stock": make_stock(),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(txs)} transactions, {len(sales)} invoices, {len(payments)} payments -> {OUT}")


if __name__ == "__main__":
    main()
