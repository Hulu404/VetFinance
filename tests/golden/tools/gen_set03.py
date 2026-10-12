"""Generates tests/golden/set03/data.json deterministically (fixed LCG, no randomness).

Set 03: one invented clinic, 3 doctors, 2026-08-01 .. 2026-09-21.
Input for the dashboard (stage 2): accounts, operations, Vetmanager sales/visits, norms.
Expected numbers are NOT computed here: see compute_expected_set03.py.
"""
import json
import pathlib
from datetime import date, timedelta

OUT = pathlib.Path(__file__).resolve().parent.parent / "set03" / "data.json"
CID = "S3"
START, LAST_SALE_DAY = date(2026, 8, 1), date(2026, 9, 20)
VACATION = (date(2026, 9, 10), date(2026, 9, 20))  # doctor D2 is away: fewer visits
COMMISSION_BP = 190  # acquiring 1.9%, taken from the bank credit

_state = 20260901


def rnd(lo, hi):
    global _state
    _state = (_state * 1103515245 + 12345) % (2**31)
    return lo + (_state >> 8) % (hi - lo + 1)


DOCTORS = [{"id": "D1", "name": "Ильина М."}, {"id": "D2", "name": "Петров А."}, {"id": "D3", "name": "Соколова Е."}]
ACCOUNTS = [
    {"id": "S3-bank", "clinic_id": CID, "name": "Расчётный счёт", "type": "bank", "opening_balance": 38_650_017, "opening_date": "2026-08-01"},
    {"id": "S3-reserve", "clinic_id": CID, "name": "Резервный счёт", "type": "bank", "opening_balance": 2_000_000, "opening_date": "2026-08-01"},
    {"id": "S3-cash", "clinic_id": CID, "name": "Касса", "type": "cash", "opening_balance": 650_050, "opening_date": "2026-08-01"},
]


def make_sales():
    sales, visits = [], []
    d = START
    while d <= LAST_SALE_DAY:
        weekend = d.weekday() >= 5
        away = VACATION[0] <= d <= VACATION[1]
        n = rnd(7, 9) if weekend else rnd(11, 14)
        if away:
            n = max(3, n // 2)
        for _ in range(n):
            doc = rnd(0, 2)
            if away and doc == 1:
                doc = 0 if rnd(0, 1) else 2
            lines = []
            has_service = rnd(1, 10) <= 7
            if has_service:
                lines.append({"kind": "service", "amount": rnd(60_000, 520_000) + rnd(0, 99) * rnd(0, 1)})
            if not has_service or rnd(1, 10) <= 5:
                lines.append({"kind": "good", "amount": rnd(25_000, 380_000) + rnd(0, 99) * rnd(0, 1)})
            sid = f"vm-inv-{len(sales) + 1:04d}"
            status = "save" if rnd(1, 100) <= 3 else "exec"
            sales.append({"id": sid, "date": d.isoformat(), "status": status,
                          "pay": "cash" if rnd(1, 10) <= 3 else "card", "doctor_id": DOCTORS[doc]["id"],
                          "amount": sum(x["amount"] for x in lines), "lines": lines})
            if has_service:
                visits.append({"id": f"vm-visit-{len(visits) + 1:04d}", "date": d.isoformat(), "doctor_id": DOCTORS[doc]["id"]})
        d += timedelta(days=1)
    return sales, visits


def make_transactions(sales):
    txs = []

    def add(acc, d, desc, cat, src, kind, amount, status="ok", group=None):
        t = {"id": "", "clinic_id": CID, "account_id": f"{CID}-{acc}",
             "date": d.isoformat(), "description": desc, "category": cat, "source": src,
             "kind": kind, "amount": amount, "status": status}
        if group:
            t["transfer_group"] = group
        txs.append(t)

    # revenue money: cash on the day of the sale, card credit next day minus acquiring commission
    by_day = {}
    for s in sales:
        if s["status"] != "exec":
            continue
        day = by_day.setdefault(s["date"], {"cash": 0, "card": 0})
        day[s["pay"]] += s["amount"]
    for ds in sorted(by_day):
        d = date.fromisoformat(ds)
        if by_day[ds]["cash"]:
            add("cash", d, "Оплата наличными за день", "Выручка наличные", "vetmanager", "in", by_day[ds]["cash"])
        card = by_day[ds]["card"]
        if card:
            credit = card - (card * COMMISSION_BP + 5_000) // 10_000
            add("bank", d + timedelta(days=1), f"Эквайринг: зачисление за {d.strftime('%d.%m')}", "Выручка эквайринг", "bank", "in", credit)

    D = date
    exp = [  # (account, date, description, category, source, amount)
        ("bank", D(2026, 8, 5), "Аренда помещения", "Аренда", "bank", -12_000_000),
        ("bank", D(2026, 8, 10), "Зарплата, аванс", "Зарплата", "bank", -14_000_000),
        ("bank", D(2026, 8, 25), "Зарплата, расчёт", "Зарплата", "bank", -14_520_050),
        ("bank", D(2026, 8, 15), "Коммунальные услуги", "Коммунальные и связь", "bank", -1_874_035),
        ("bank", D(2026, 8, 15), "Связь и интернет", "Коммунальные и связь", "bank", -320_000),
        ("bank", D(2026, 8, 20), "Реклама в соцсетях", "Реклама", "bank", -1_500_000),
        ("bank", D(2026, 8, 18), "Налоги и взносы", "Налоги и взносы", "bank", -5_830_040),
        ("bank", D(2026, 8, 4), "ООО «Зоовет», закупка препаратов", "Препараты и расходники", "bank", -7_840_030),
        ("bank", D(2026, 8, 12), "ООО «Зоовет», закупка препаратов", "Препараты и расходники", "bank", -6_625_000),
        ("bank", D(2026, 8, 19), "ООО «Вет-Снаб», закупка препаратов", "Препараты и расходники", "bank", -9_173_045),
        ("bank", D(2026, 8, 27), "ООО «Зоовет», закупка препаратов", "Препараты и расходники", "bank", -7_011_890),
        ("bank", D(2026, 8, 28), "Оборудование: УЗИ-датчик", "Прочие расходы", "bank", -9_800_000),
        ("cash", D(2026, 8, 9), "Хозрасходы из кассы", "Прочие расходы", "manual", -184_000),
        ("cash", D(2026, 8, 23), "Хозрасходы из кассы", "Прочие расходы", "manual", -256_070),
        ("bank", D(2026, 9, 1), "Аренда помещения", "Аренда", "bank", -12_000_000),
        ("bank", D(2026, 9, 3), "ООО «Зоовет», закупка препаратов", "Препараты и расходники", "bank", -13_460_040),
        ("bank", D(2026, 9, 4), "Связь и интернет", "Коммунальные и связь", "bank", -320_000),
        ("cash", D(2026, 9, 5), "Хозрасходы из кассы", "Прочие расходы", "manual", -143_500),
        ("bank", D(2026, 9, 8), "Реклама в соцсетях", "Реклама", "bank", -1_500_000),
        ("bank", D(2026, 9, 10), "Зарплата, аванс", "Зарплата", "bank", -14_000_000),   # after as_of 09-09
        ("bank", D(2026, 9, 12), "ООО «Зоовет», закупка препаратов", "Препараты и расходники", "bank", -7_200_000),
        ("bank", D(2026, 9, 15), "Коммунальные услуги", "Коммунальные и связь", "bank", -1_912_060),
        ("bank", D(2026, 9, 18), "Налоги и взносы", "Налоги и взносы", "bank", -5_830_040),
        ("bank", D(2026, 9, 18), "ООО «Вет-Снаб», закупка препаратов", "Препараты и расходники", "bank", -6_548_020),
        ("cash", D(2026, 9, 19), "Хозрасходы из кассы", "Прочие расходы", "manual", -212_000),
    ]
    for acc, d, desc, cat, src, amount in exp:
        add(acc, d, desc, cat, src, "out", amount)

    # a payment entered by the bot and the same payment from the statement a day later: the statement copy is the duplicate
    add("bank", D(2026, 8, 21), "Оплата поставщику кормов (бот)", "Корма для перепродажи", "bot", "out", -4_800_000)
    add("bank", D(2026, 8, 22), "ООО «Корм-Опт», оплата кормов", "Корма для перепродажи", "bank", "out", -4_800_000, status="duplicate")
    add("bank", D(2026, 9, 5), "Оплата поставщику кормов (бот)", "Корма для перепродажи", "bot", "out", -5_400_000)
    add("bank", D(2026, 9, 6), "ООО «Корм-Опт», оплата кормов", "Корма для перепродажи", "bank", "out", -5_400_000, status="duplicate")
    # unrecognised debit and credit: count in the balance; the debit counts in expenses under "Без статьи"
    add("bank", D(2026, 9, 7), "Списание, назначение не распознано", None, "bank", "out", -124_000, status="check")
    add("bank", D(2026, 8, 30), "Поступление от ИП Кузнецов, назначение не распознано", None, "bank", "in", 940_000, status="check")
    # transfers between own accounts (two legs each)
    moves = [(D(2026, 8, 8), "cash", "bank", 4_000_000), (D(2026, 8, 16), "cash", "bank", 10_000_000),
             (D(2026, 8, 20), "bank", "reserve", 5_000_000), (D(2026, 8, 30), "cash", "bank", 10_000_000),
             (D(2026, 9, 2), "cash", "bank", 3_000_000), (D(2026, 9, 12), "cash", "bank", 10_000_000),
             (D(2026, 9, 14), "reserve", "bank", 2_500_000), (D(2026, 9, 19), "cash", "bank", 6_000_000)]
    for n, (d, a, b, amt) in enumerate(moves, 1):
        g = f"S3-trf-{n}"
        src = "manual" if "cash" in (a, b) else "bank"
        add(a, d, "Перевод между счетами", None, src, "transfer", -amt, group=g)
        add(b, d, "Перевод между счетами", None, src, "transfer", amt, group=g)
    txs.sort(key=lambda t: (t["date"], t["account_id"], t["amount"]))
    for i, t in enumerate(txs, 1):  # ids follow the date order
        t["id"] = f"{CID}-tx-{i:03d}"
    return txs


def main():
    sales, visits = make_sales()
    txs = make_transactions(sales)
    data = {
        "as_of_cases": ["2026-08-04", "2026-08-31", "2026-09-09", "2026-09-20"],
        "clinic": {"id": CID, "name": "Ветеринарная клиника «Лапа»", "timezone": "Europe/Moscow", "safe_balance": 15_000_000},
        "doctors": DOCTORS,
        "norms": {  # clinic settings until the benchmarks table (stage 3); integer percents
            "drugs": {"category": "Препараты и расходники", "min_pct": 18, "max_pct": 25},
            "profit_margin": {"min_pct": 12, "max_pct": 20},
        },
        "accounts": ACCOUNTS,
        "transactions": txs,
        "sales": sales,
        "visits": visits,
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(txs)} transactions, {len(sales)} invoices, {len(visits)} visits -> {OUT}")


if __name__ == "__main__":
    main()
