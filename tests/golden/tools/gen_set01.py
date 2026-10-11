"""Generates tests/golden/set01/data.json deterministically (fixed LCG, no randomness).

The generated file is committed; this script only documents how it was built.
Expected numbers are NOT computed here: see compute_expected_set01.py.
"""
import json
import pathlib
from datetime import date, timedelta

OUT = pathlib.Path(__file__).resolve().parent.parent / "set01" / "data.json"

_state = 20260801


def rnd(lo, hi):
    """Deterministic LCG; returns int in [lo, hi]."""
    global _state
    _state = (_state * 1103515245 + 12345) % (2**31)
    return lo + _state % (hi - lo + 1)


def build_clinic(cid, accounts, plan_days, extra):
    txs = []
    n = 0

    def add(acc, d, desc, cat, src, kind, amount, status="ok", group=None):
        nonlocal n
        n += 1
        t = {"id": f"{cid}-tx-{n:03d}", "clinic_id": cid, "account_id": f"{cid}-{acc}",
             "date": d.isoformat(), "description": desc, "category": cat,
             "source": src, "kind": kind, "amount": amount, "status": status}
        if group:
            t["transfer_group"] = group
        txs.append(t)

    start = date(2026, 8, 1)
    for day in plan_days:
        d = start + timedelta(days=day)
        add("bank", d, "Эквайринг: зачисление за смену", "Выручка", "bank", "in", rnd(18000_00, 95000_00) + rnd(0, 99))
        if day % 3 == 0:
            add("cash", d, "Приём наличных за смену", "Выручка", "vetmanager", "in", rnd(2500_00, 21000_00) + rnd(0, 99))
        if day % 5 == 1:
            add("bank", d, "Оплата поставщику препаратов", "Лекарства", "bank", "out", -(rnd(8000_00, 60000_00) + rnd(0, 99)))
        if day % 11 == 4:
            add("cash", d, "Хозрасходы из кассы", "Хозяйственные", "manual", "out", -(rnd(300_00, 4000_00) + rnd(0, 99)))
    extra(add)
    return txs


def extra_a(add):
    d = date
    add("bank", d(2026, 8, 5), "Аренда помещения", "Аренда", "bank", "out", -12000000)
    add("bank", d(2026, 8, 25), "Зарплата врачей", "Зарплата", "bank", "out", -28450075)
    add("bank", d(2026, 9, 5), "Аренда помещения", "Аренда", "bank", "out", -12000000)
    add("bank", d(2026, 9, 25), "Зарплата врачей", "Зарплата", "bank", "out", -28450075)
    # transfers: each is two legs, net zero for the clinic total
    add("bank", d(2026, 8, 10), "Снятие наличных в кассу", None, "bank", "transfer", -5000000, group="A-trf-1")
    add("cash", d(2026, 8, 10), "Снятие наличных в кассу", None, "manual", "transfer", 5000000, group="A-trf-1")
    add("cash", d(2026, 8, 20), "Инкассация выручки на счёт", None, "manual", "transfer", -3500050, group="A-trf-2")
    add("bank", d(2026, 8, 21), "Взнос наличных на счёт", None, "bank", "transfer", 3500050, group="A-trf-2")
    add("bank", d(2026, 9, 2), "Перевод на резервный счёт", None, "bank", "transfer", -15000000, group="A-trf-3")
    add("bank2", d(2026, 9, 2), "Перевод с основного счёта", None, "bank", "transfer", 15000000, group="A-trf-3")
    add("bank2", d(2026, 9, 8), "Проценты на остаток", "Проценты", "bank", "in", 12345)
    add("bank", d(2026, 9, 12), "Перевод на резервный счёт", None, "bank", "transfer", -2000000, group="A-trf-4")
    add("bank2", d(2026, 9, 12), "Перевод с основного счёта", None, "bank", "transfer", 2000000, group="A-trf-4")
    # duplicate: same payment seen from bot and from bank statement
    add("bank", d(2026, 9, 4), "Оплата коммунальных услуг", "Коммунальные", "bank", "out", -1875033)
    add("bank", d(2026, 9, 4), "Оплата коммунальных услуг (бот)", "Коммунальные", "bot", "out", -1875033, status="duplicate")
    add("cash", d(2026, 9, 6), "Закупка корма из кассы (дубль ручного ввода)", "Хозяйственные", "manual", "out", -240000, status="duplicate")
    add("cash", d(2026, 9, 6), "Закупка корма из кассы", "Хозяйственные", "manual", "out", -240000)
    # needs-check operation: counts in balance (money really moved)
    add("bank", d(2026, 9, 7), "Платёж без назначения", None, "bank", "out", -777700, status="check")
    # exactly on as_of 2026-09-09 and after it
    add("bank", d(2026, 9, 9), "Поступление за приём (на дату as_of)", "Выручка", "bank", "in", 4321099)
    add("bank", d(2026, 9, 10), "Эквайринг после as_of", "Выручка", "bank", "in", 9999999)
    add("cash", d(2026, 9, 15), "Расход после as_of", "Хозяйственные", "manual", "out", -100000)


def extra_b(add):
    d = date
    add("bank", d(2026, 8, 5), "Аренда помещения", "Аренда", "bank", "out", -9000000)
    add("bank", d(2026, 8, 12), "Перевод в кассу", None, "bank", "transfer", -1000000, group="B-trf-1")
    add("cash", d(2026, 8, 12), "Перевод в кассу", None, "manual", "transfer", 1000000, group="B-trf-1")
    add("bank", d(2026, 8, 20), "Платёж-дубль", "Лекарства", "bank", "out", -3300000)
    add("bank", d(2026, 8, 20), "Платёж-дубль (бот)", "Лекарства", "bot", "out", -3300000, status="duplicate")
    add("bank", d(2026, 9, 10), "Эквайринг после as_of", "Выручка", "bank", "in", 5000000)


def main():
    clinics = [
        {"id": "A", "name": "Клиника «Лапа» (набор A)", "timezone": "Europe/Moscow", "safe_balance": 15000000},
        {"id": "B", "name": "Клиника «Хвост» (набор B)", "timezone": "Europe/Moscow", "safe_balance": 5000000},
    ]
    accounts = [
        {"id": "A-bank", "clinic_id": "A", "name": "Расчётный счёт", "type": "bank", "opening_balance": 125000037, "opening_date": "2026-08-01"},
        {"id": "A-bank2", "clinic_id": "A", "name": "Резервный счёт", "type": "bank", "opening_balance": 30000000, "opening_date": "2026-08-01"},
        {"id": "A-cash", "clinic_id": "A", "name": "Касса", "type": "cash", "opening_balance": 4532050, "opening_date": "2026-08-01"},
        {"id": "B-bank", "clinic_id": "B", "name": "Расчётный счёт", "type": "bank", "opening_balance": 40000000, "opening_date": "2026-08-01"},
        {"id": "B-cash", "clinic_id": "B", "name": "Касса", "type": "cash", "opening_balance": 1500099, "opening_date": "2026-08-01"},
    ]
    txs = build_clinic("A", accounts, list(range(0, 44, 2)), extra_a)
    txs += build_clinic("B", accounts, list(range(1, 40, 6)), extra_b)
    data = {"as_of_cases": ["2026-08-31", "2026-09-09", "2026-09-30"],
            "clinics": clinics, "accounts": accounts, "transactions": txs}
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(len(txs), "transactions")


if __name__ == "__main__":
    main()
