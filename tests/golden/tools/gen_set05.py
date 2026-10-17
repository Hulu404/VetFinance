"""Generates tests/golden/set05/data.json deterministically (fixed LCG, no randomness).

Set 05: one invented clinic F «Сосна», bank history 2026-04-01 .. 2026-10-06, stage 4 "Платёжный календарь и Обязательства"
(functions 21, 22, 23, 43). The calendar date is as_of = 2026-10-07 (statement through yesterday).
What is DESIGNED here (tables SERIES_*, WEEKDAY_*, OBLIGATIONS): regular payments with weekend shifts and small amount noise,
one-off payments that must NOT become regular, the weekly revenue profile, a loan, a lease, equipment.
Expected numbers are NOT computed here: see compute_expected_set05.py (reads only data.json).
Run: python tests/golden/tools/gen_set05.py
"""
import json
import pathlib
from datetime import date, timedelta

OUT = pathlib.Path(__file__).resolve().parent.parent / "set05" / "data.json"
CID = "S5"
HISTORY_FROM, HISTORY_TO = date(2026, 4, 1), date(2026, 10, 6)
AS_OF = date(2026, 10, 7)
MONTHS = ["2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"]
SAFE_BALANCE = 15_000_000          # 150 000 ₽
CASH_FLOAT = 2_000_000             # the cash desk keeps 20 000 ₽, the rest goes to the bank every Tuesday

_state = 20261016


def rnd(lo, hi):
    global _state
    _state = (_state * 1103515245 + 12345) % (2**31)
    return lo + (_state >> 8) % (hi - lo + 1)


def is_workday(d):
    return d.weekday() < 5     # Monday..Friday; no holiday calendar (README, rule 4)


def shift(d, direction):
    step = timedelta(days=-1 if direction == "prev" else 1)
    while not is_workday(d):
        d += step
    return d


def nominal(month, day):
    y, m = map(int, month.split("-"))
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    return date(y, m, min(day, (nxt - timedelta(days=1)).day))


ACCOUNTS = [
    {"id": "S5-bank", "clinic_id": CID, "name": "Расчётный счёт", "type": "bank", "opening_balance": 31_000_000,
     "opening_date": "2026-04-01"},
    {"id": "S5-cash", "clinic_id": CID, "name": "Касса", "type": "cash", "opening_balance": 1_500_000, "opening_date": "2026-04-01"},
]

CATEGORIES = [  # name, type
    ("Выручка наличные", "income"), ("Выручка эквайринг", "income"),
    ("Препараты и расходники", "variable"), ("Корма для перепродажи", "variable"), ("Лаборатории", "variable"),
    ("Оклады", "fixed"), ("Аренда", "fixed"), ("Коммунальные и связь", "fixed"), ("Хозяйственные расходы", "fixed"),
    ("Реклама", "fixed"), ("Программы и сервисы", "fixed"), ("Ремонт оборудования", "fixed"),
    ("Налоги и взносы", "tax"), ("Платежи по кредитам и лизингу", "obligation"), ("Покупка оборудования", "capex"),
    ("Вывод средств владельца", "owner_draw"),
]

# counterparty settings: how many days a payment may be postponed by the contract (README, rule 13)
COUNTERPARTIES = [
    {"inn": "5003012345", "name": "ООО «Зоовет»", "max_deferral_days": 5},
    {"inn": "7714556677", "name": "ООО «ВетПрепарат»", "max_deferral_days": 3},
    {"inn": "7728990011", "name": "ООО «Чистый дом»", "max_deferral_days": 3},
    {"inn": "772800112233", "name": "ИП Кравцов А. В.", "max_deferral_days": 0},
]

# ---------------------------------------------------------------- DESIGN: payments from the bank, kopecks, April..September
# key: (inn, counterparty, category, nominal day, shift direction on a day off, amounts Apr..Sep, {month: actual day override})
SERIES_REGULAR = [
    ("772800112233", "ИП Кравцов А. В.", "Аренда", 8, "prev", [14_000_000] * 6, {}),
    ("7707083893", "Сбербанк (зарплатный проект)", "Оклады", 10, "prev",
     [28_400_000, 28_900_000, 29_200_000, 28_750_000, 29_600_000, 29_050_000], {}),
    ("7707083893", "Сбербанк (зарплатный проект)", "Оклады", 25, "prev",
     [11_800_000, 12_000_000, 12_000_000, 12_100_000, 12_300_000, 12_200_000], {}),
    ("5003012345", "ООО «Зоовет»", "Препараты и расходники", 7, "prev",
     [10_120_000, 9_875_050, 10_640_000, 10_412_300, 11_230_000, 10_850_000], {}),
    ("5003012345", "ООО «Зоовет»", "Препараты и расходники", 21, "prev",
     [9_600_000, 10_050_000, 9_870_000, 10_230_000, 9_940_500, 10_480_000], {}),
    ("7714556677", "ООО «ВетПрепарат»", "Препараты и расходники", 20, "prev",
     [5_800_000, 6_150_000, 5_920_000, 6_040_000, 5_760_000, 6_310_000], {"2026-08": 21}),   # paid a day late once
    ("7810443322", "ООО «Шанс Био»", "Лаборатории", 13, "prev",
     [3_210_000, 3_480_000, 3_390_000, 3_620_000, 3_350_000, 3_540_000], {}),
    ("7701234500", "АО «Горэнерго»", "Коммунальные и связь", 12, "prev",
     [2_112_040, 1_734_518, 1_498_233, 1_552_090, 1_603_377, 1_748_912], {}),
    ("7707049388", "ПАО «Ростелеком»", "Коммунальные и связь", 18, "prev", [730_000] * 6, {}),
    ("7728990011", "ООО «Чистый дом»", "Хозяйственные расходы", 8, "prev",
     [912_000, 864_500, 958_000, 905_300, 871_000, 940_200], {}),
    ("7727406020", "УФК (ФНС России), ЕНП", "Налоги и взносы", 28, "next",
     [5_980_000, 6_120_000, 5_760_000, 5_840_000, 6_310_000, 6_125_000], {}),
    ("7720112244", "ЧОП «Щит»", None, 16, "prev", [600_000] * 6, {}),    # no article: status "check"
]

# one-off and irregular payments: must NOT become regular (README, rule 9)
ONE_OFF = [  # date, inn, counterparty, category, amount
    ("2026-04-06", "7736207543", "ООО «Яндекс»", "Реклама", 1_500_000),
    ("2026-05-05", "7736207543", "ООО «Яндекс»", "Реклама", 4_000_000),
    ("2026-06-05", "7736207543", "ООО «Яндекс»", "Реклама", 800_000),
    ("2026-07-06", "7736207543", "ООО «Яндекс»", "Реклама", 2_200_000),
    ("2026-08-05", "7736207543", "ООО «Яндекс»", "Реклама", 900_000),
    ("2026-09-07", "7736207543", "ООО «Яндекс»", "Реклама", 3_500_000),
    ("2026-10-05", "7736207543", "ООО «Яндекс»", "Реклама", 1_200_000),
    ("2026-04-03", "7725667788", "ООО «ВетКлауд»", "Программы и сервисы", 399_000),
    ("2026-05-04", "7725667788", "ООО «ВетКлауд»", "Программы и сервисы", 399_000),
    ("2026-06-03", "7725667788", "ООО «ВетКлауд»", "Программы и сервисы", 399_000),
    ("2026-07-03", "7725667788", "ООО «ВетКлауд»", "Программы и сервисы", 399_000),
    ("2026-07-15", "5012345678", "АО «Роял Канин»", "Корма для перепродажи", 4_800_000),
    ("2026-09-15", "5012345678", "АО «Роял Канин»", "Корма для перепродажи", 5_100_000),
    ("2026-08-19", "7716998877", "ООО «Медтехсервис»", "Ремонт оборудования", 2_750_000),
    ("2026-09-14", "7743001122", "ООО «Лабтех»", "Покупка оборудования", 8_500_000),
    ("2026-05-29", "", "Собственник", "Вывод средств владельца", 18_000_000),
    ("2026-06-30", "", "Собственник", "Вывод средств владельца", 20_000_000),
    ("2026-07-31", "", "Собственник", "Вывод средств владельца", 25_000_000),
    ("2026-09-30", "", "Собственник", "Вывод средств владельца", 43_000_000),
    ("2026-10-02", "7707049388", "ПАО «Ростелеком»", "Коммунальные и связь", 730_000),   # October paid early
]

# obligations (function 23). The loan and lease payments are also in the bank (category of type obligation).
OBLIGATIONS = [
    {"id": "S5-loan", "kind": "loan", "name": "Кредит на аппарат УЗИ", "lender": "Сбербанк", "counterparty_inn": "7707083893",
     "principal": 150_000_000, "annual_rate_bp": 1600, "payment": 5_273_500, "payment_day": 8,
     "first_payment_date": "2025-11-08", "payments_total": 36},
    {"id": "S5-lease", "kind": "lease", "name": "Лизинг рентген-аппарата", "lender": "АО «Европлан»",
     "counterparty_inn": "7705123456", "payment": 2_500_000, "payment_day": 15, "first_payment_date": "2024-04-15",
     "payments_total": 36},
    {"id": "S5-eq-us", "kind": "equipment", "name": "Аппарат УЗИ", "cost": 168_000_000, "life_years": 7,
     "in_service_date": "2025-10-20"},
    {"id": "S5-eq-blood", "kind": "equipment", "name": "Анализатор крови", "cost": 25_000_000, "life_years": 5,
     "in_service_date": "2024-02-10"},
    {"id": "S5-eq-centr", "kind": "equipment", "name": "Центрифуга", "cost": 8_500_000, "life_years": 3,
     "in_service_date": "2026-09-14"},
    {"id": "S5-eq-autoclave", "kind": "equipment", "name": "Автоклав", "cost": 11_800_000, "life_years": 5,
     "in_service_date": "2021-04-05"},
]
LOAN_PAYMENTS_HISTORY = {"S5-loan": "Сбербанк", "S5-lease": "АО «Европлан»"}

PLANNED = [{"id": "S5-plan-1", "date": "2026-10-14", "name": "Ремонт кондиционера", "amount": 4_500_000, "max_deferral_days": 0}]

# ---------------------------------------------------------------- DESIGN: money in, kopecks per weekday (Mon..Sun)
WEEKDAY_CARD = [6_400_000, 3_000_000, 3_100_000, 2_950_000, 3_300_000, 0, 0]       # acquiring settlement, business days
WEEKDAY_CASH = [1_700_000, 1_150_000, 1_200_000, 1_100_000, 1_400_000, 2_100_000, 1_450_000]
NOISE_PCT = 6


def noisy(base):
    if base == 0:
        return 0
    delta = base * NOISE_PCT // 100
    return base + rnd(-delta, delta) + rnd(0, 99)


def main():
    txs = []

    def add(d, account, amount, kind, category, inn="", name="", status="ok", source="bank", description=""):
        txs.append({"id": f"S5-t{len(txs) + 1:04d}", "account_id": account, "date": d.isoformat(), "amount": amount,
                    "kind": kind, "status": status, "source": source, "category": category,
                    "counterparty_inn": inn, "counterparty_name": name, "description": description})

    cash = ACCOUNTS[1]["opening_balance"]
    d = HISTORY_FROM
    while d <= HISTORY_TO:
        wd = d.weekday()
        card = noisy(WEEKDAY_CARD[wd])
        if card:
            add(d, "S5-bank", card, "in", "Выручка эквайринг", "7707083893", "Сбербанк (эквайринг)",
                description="Зачисление по эквайрингу за вычетом комиссии")
        cash_in = noisy(WEEKDAY_CASH[wd])
        add(d, "S5-cash", cash_in, "in", "Выручка наличные", source="vetmanager", description="Выручка наличными за день")
        cash += cash_in
        if wd == 1 and cash > CASH_FLOAT:              # Tuesday: cash to the bank (a transfer, not income)
            move = (cash - CASH_FLOAT) // 100_000 * 100_000
            add(d, "S5-cash", -move, "transfer", None, source="vetmanager", description="Сдача наличных в банк")
            add(d, "S5-bank", move, "transfer", None, description="Взнос наличных")
            cash -= move
        d += timedelta(days=1)

    for inn, name, category, day, direction, amounts, override in SERIES_REGULAR:
        for month, amount in zip(MONTHS, amounts):
            pay = nominal(month, override[month]) if month in override else shift(nominal(month, day), direction)
            add(pay, "S5-bank", -amount, "out", category, inn, name, status="ok" if category else "check",
                description=f"Оплата по договору, {month}")

    for day, inn, name, category, amount in ONE_OFF:
        add(date.fromisoformat(day), "S5-bank", -amount, "out", category, inn, name, description="Оплата")

    # loan and lease payments (bank side of the obligations) inside the history
    for ob in OBLIGATIONS:
        if ob["kind"] not in ("loan", "lease"):
            continue
        first = date.fromisoformat(ob["first_payment_date"])
        y, m = first.year, first.month
        for n in range(ob["payments_total"]):
            month = f"{y + (m - 1 + n) // 12}-{(m - 1 + n) % 12 + 1:02d}"
            pay = shift(nominal(month, ob["payment_day"]), "prev")
            if HISTORY_FROM <= pay <= HISTORY_TO:
                add(pay, "S5-bank", -ob["payment"], "out", "Платежи по кредитам и лизингу", ob["counterparty_inn"],
                    LOAN_PAYMENTS_HISTORY[ob["id"]], description=f"Платёж по графику, {month}")

    # traps: a duplicate (bot entry of the July rent), money in that is not revenue, a duplicate settlement
    add(date(2026, 7, 8), "S5-bank", -14_000_000, "out", "Аренда", "772800112233", "ИП Кравцов А. В.", status="duplicate",
        source="bot", description="Аренда за июль (внесено через бот)")
    add(date(2026, 8, 26), "S5-bank", 1_250_000, "in", "Препараты и расходники", "5003012345", "ООО «Зоовет»",
        description="Возврат за бракованную партию")
    add(date(2026, 9, 16), "S5-bank", 870_000, "in", None, "", "", status="check", description="Поступление без назначения")
    first_sep8 = next(t for t in txs if t["date"] == "2026-09-08" and t["category"] == "Выручка эквайринг")
    add(date(2026, 9, 8), "S5-bank", first_sep8["amount"], "in", "Выручка эквайринг", "7707083893", "Сбербанк (эквайринг)",
        status="duplicate", description="Зачисление по эквайрингу (повтор выписки)")

    txs.sort(key=lambda t: (t["date"], t["id"]))
    data = {
        "set": "05", "as_of": AS_OF.isoformat(), "window_days": 22,
        "history": {"from": HISTORY_FROM.isoformat(), "to": HISTORY_TO.isoformat()},
        "clinic": {"id": CID, "name": "Ветклиника «Сосна» (набор F)", "timezone": "Europe/Moscow", "safe_balance": SAFE_BALANCE},
        "accounts": ACCOUNTS,
        "categories": [{"name": n, "type": t} for n, t in CATEGORIES],
        "counterparties": COUNTERPARTIES,
        "obligations": OBLIGATIONS,
        "planned_payments": PLANNED,
        "transactions": txs,
        "cases": [
            {"key": "main", "as_of": AS_OF.isoformat(), "safe_balance": SAFE_BALANCE},
            {"key": "high_safe", "as_of": AS_OF.isoformat(), "safe_balance": 25_000_000},
        ],
        "charge_months": ["2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"written {OUT} ({len(txs)} transactions)")


if __name__ == "__main__":
    main()
