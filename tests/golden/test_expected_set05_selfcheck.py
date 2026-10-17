"""Internal consistency of set05 (runs without the engine): data.json is sane, expected.json is coherent, agrees with hand-typed
design values (README, «Что задумано» and «Ключевые числа») and with a second, differently written calculation (Decimal,
per-day dictionaries, the move checked by hand)."""
from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

import pytest

from set05_support import AS_OF, DATA, EXPECTED, contains_amount

D = date.fromisoformat
CAL = EXPECTED["calendar"]
MAIN = CAL["main"]
OBL = EXPECTED["obligations"]
SAFE = DATA["clinic"]["safe_balance"]
CAT_TYPE = {c["name"]: c["type"] for c in DATA["categories"]}

# Hand-typed window of the main case (kopecks): date -> [(name, amount, source)]. From the README table, not from code.
HAND_PAYMENTS = {
    "2026-10-07": [("ООО «Зоовет»", 10_850_000, "recurring")],
    "2026-10-08": [("ИП Кравцов А. В.", 14_000_000, "recurring"), ("Кредит на аппарат УЗИ", 5_273_500, "obligation"),
                   ("ООО «Чистый дом»", 905_300, "recurring")],
    "2026-10-09": [("Сбербанк (зарплатный проект)", 29_050_000, "recurring")],
    "2026-10-12": [("АО «Горэнерго»", 1_603_377, "recurring")],
    "2026-10-13": [("ООО «Шанс Био»", 3_540_000, "recurring")],
    "2026-10-14": [("Ремонт кондиционера", 4_500_000, "manual")],
    "2026-10-15": [("Лизинг рентген-аппарата", 2_500_000, "obligation")],
    "2026-10-16": [("ЧОП «Щит»", 600_000, "recurring")],
    "2026-10-20": [("ООО «ВетПрепарат»", 6_040_000, "recurring")],
    "2026-10-21": [("ООО «Зоовет»", 10_230_000, "recurring")],
    "2026-10-23": [("Сбербанк (зарплатный проект)", 12_200_000, "recurring")],
    "2026-10-28": [("УФК (ФНС России), ЕНП", 6_125_000, "recurring")],
}
HAND_PROFILE = [8_104_608, 4_093_149, 4_287_345, 4_034_914, 4_732_431, 2_075_402, 1_437_186]   # Mon..Sun, README
HAND = {"opening": 54_357_728, "opening_bank": 52_325_696, "opening_cash": 2_032_032,
        "lowest": ("2026-10-09", 7_333_618), "shortfall": 7_666_382, "red": ["2026-10-09", "2026-10-10", "2026-10-11"],
        "income": 90_582_450, "expense": 107_417_177, "count": 14, "last_closing": 37_523_001,
        "after": {"2026-10-09": 18_183_618, "2026-10-10": 20_259_020, "2026-10-11": 21_696_206, "2026-10-12": 17_347_437}}
HAND_OBL = {"loan_remaining": 111_492_301, "lease_remaining": 15_000_000, "debt_total": 126_492_301,
            "monthly_payment": 5_273_500 + 2_500_000, "amortization_oct": 2_000_000 + 416_667 + 236_111,
            "interest_oct": 1_486_564, "charges_oct": 1_486_564 + 2_500_000 + 2_000_000 + 416_667 + 236_111,
            "charges_sep": 1_536_392 + 2_500_000 + 2_000_000 + 416_667, "autoclave_last": 11_800_000 - 59 * 196_667}
NOT_REGULAR = {"ООО «Яндекс»", "ООО «ВетКлауд»", "АО «Роял Канин»", "ООО «Медтехсервис»", "ООО «Лабтех»", "Собственник"}


def half_up(x: Decimal) -> int:
    return int(x.quantize(Decimal(1), rounding=ROUND_HALF_UP))


# ---------------------------------------------------------------- data.json
def test_money_is_integer_kopecks_and_history_ends_the_day_before_as_of():
    txs = DATA["transactions"]
    assert all(type(t["amount"]) is int and t["amount"] != 0 for t in txs)
    assert sum(1 for t in txs if t["amount"] % 100) > 100
    assert max(t["date"] for t in txs) == DATA["history"]["to"] == (AS_OF - timedelta(days=1)).isoformat()
    assert min(t["date"] for t in txs) == DATA["history"]["from"]
    assert all(t["category"] is None or t["category"] in CAT_TYPE for t in txs)


def test_transfers_net_to_zero_and_traps_are_present():
    transfers = defaultdict(int)
    for t in DATA["transactions"]:
        if t["kind"] == "transfer":
            transfers[t["date"]] += t["amount"]
    assert transfers and all(x == 0 for x in transfers.values())
    statuses = {t["status"] for t in DATA["transactions"]}
    assert statuses == {"ok", "check", "duplicate"}
    assert any(t["kind"] == "in" and t["category"] and CAT_TYPE[t["category"]] != "income" for t in DATA["transactions"])


def test_bank_payments_of_the_loan_and_lease_follow_the_schedule():
    loan = [t for t in DATA["transactions"] if t["category"] == "Платежи по кредитам и лизингу"]
    sched = {r["date"]: r["payment"] for r in EXPECTED["loan_schedule"]}
    loan_bank = [t for t in loan if t["counterparty_inn"] == "7707083893"]
    assert len(loan_bank) == 6 and all(sched[t["date"]] == -t["amount"] for t in loan_bank)
    assert len([t for t in loan if t["counterparty_inn"] == "7705123456"]) == 6


# ---------------------------------------------------------------- calendar, hand-typed values
def test_window_payments_equal_the_hand_typed_table():
    got = {d["date"]: sorted((p["name"], p["amount"], p["source"]) for p in d["payments"]) for d in MAIN["days"] if d["payments"]}
    assert got == {k: sorted(x) for k, x in HAND_PAYMENTS.items()}


def test_income_profile_equals_the_hand_typed_one_and_a_decimal_recount():
    assert [r["average"] for r in MAIN["income_profile"]["by_weekday"]] == HAND_PROFILE
    start, end = AS_OF - timedelta(days=84), AS_OF - timedelta(days=1)
    sums = defaultdict(Decimal)
    for t in DATA["transactions"]:
        if t["kind"] == "in" and t["status"] != "duplicate" and CAT_TYPE.get(t["category"]) == "income" \
                and start <= D(t["date"]) <= end:
            sums[D(t["date"]).weekday()] += Decimal(t["amount"])
    assert [half_up(sums[i] / 12) for i in range(7)] == HAND_PROFILE


def test_days_recomputed_from_hand_values():
    bal = HAND["opening"]
    for i, d in enumerate(MAIN["days"]):
        day = AS_OF + timedelta(days=i)
        assert d["opening"] == bal, d["date"]
        bal += HAND_PROFILE[day.weekday()] - sum(a for _, a, _ in HAND_PAYMENTS.get(day.isoformat(), []))
        assert d["closing"] == bal and d["below_safe"] is (bal < SAFE), d["date"]
    assert bal == HAND["last_closing"]


def test_opening_summary_lowest_and_red_days():
    assert MAIN["opening"]["value"] == HAND["opening"] == EXPECTED["dashboard_balance_at_as_of"]
    assert [b["value"] for b in MAIN["opening"]["breakdown"]] == [HAND["opening_bank"], HAND["opening_cash"]]
    s = MAIN["summary"]
    assert (s["income"], s["expense"], s["payments_count"]) == (HAND["income"], HAND["expense"], HAND["count"])
    assert sum(b["value"] for b in s["income_by_week"]) == s["income"]
    assert sum(b["value"] for b in s["expense_by_week"]) == s["expense"]
    assert (s["lowest"]["date"], s["lowest"]["balance"]) == HAND["lowest"]
    assert [d["date"] for d in MAIN["days"] if d["below_safe"]] == HAND["red"]


def test_alert_and_the_move_checked_by_hand():
    (alert,) = MAIN["alerts"]
    assert (alert["date"], alert["end_date"], alert["shortfall"]) == ("2026-10-09", "2026-10-11", HAND["shortfall"])
    assert alert["shortfall"] == SAFE - HAND["lowest"][1]
    s = alert["suggestion"]
    assert (s["name"], s["amount"], s["from"], s["to"], s["shift_days"], s["closes_gap"]) == \
        ("ООО «Зоовет»", 10_850_000, "2026-10-07", "2026-10-12", 5, True)
    after = {x["date"]: x["closing"] for x in alert["after"]}
    for day, closing in HAND["after"].items():
        assert after[day] == closing
    assert min(after.values()) >= SAFE
    # 10th and 11th are a weekend: the only working days in reach are 8th, 9th and 12th
    tried = {(c["name"], c["to"]): c["closes_gap"] for c in alert["candidates"]}
    assert tried == {("ООО «Зоовет»", "2026-10-08"): False, ("ООО «Зоовет»", "2026-10-09"): False,
                     ("ООО «Зоовет»", "2026-10-12"): True, ("ООО «Чистый дом»", "2026-10-09"): False}


def test_the_move_by_a_second_calculation():
    """Move the payment in a copy of the hand table and roll the balance again."""
    pays = {k: list(x) for k, x in HAND_PAYMENTS.items()}
    pays["2026-10-07"] = []
    pays.setdefault("2026-10-12", []).append(("ООО «Зоовет»", 10_850_000, "recurring"))
    bal, red = HAND["opening"], []
    for i in range(22):
        day = AS_OF + timedelta(days=i)
        bal += HAND_PROFILE[day.weekday()] - sum(a for _, a, _ in pays.get(day.isoformat(), []))
        if bal < SAFE:
            red.append(day)
    assert red == []


def test_high_safe_case_has_a_partial_and_a_closing_suggestion():
    a1, a2 = CAL["high_safe"]["alerts"]
    assert (a1["date"], a1["end_date"], a1["suggestion"]["closes_gap"]) == ("2026-10-09", "2026-10-16", False)
    assert (a2["date"], a2["end_date"], a2["suggestion"]["closes_gap"]) == ("2026-10-23", "2026-10-23", True)
    assert (a2["suggestion"]["from"], a2["suggestion"]["to"]) == ("2026-10-21", "2026-10-26")
    after = {x["date"]: x["closing"] for x in a2["after"]}
    before = {d["date"]: d["closing"] for d in CAL["high_safe"]["days"]}
    assert after["2026-10-23"] == 33_880_311 >= 25_000_000
    assert all(after[k] == before[k] for k in before if k >= "2026-10-26")   # from the new date on nothing changes
    assert all(after[k] == before[k] for k in before if k < "2026-10-21")


def test_regular_and_not_regular_counterparties():
    regular = {s["name"] for s in MAIN["recurring"]}
    assert regular == {"ИП Кравцов А. В.", "Сбербанк (зарплатный проект)", "ООО «Зоовет»", "ООО «ВетПрепарат»", "ООО «Шанс Био»",
                       "АО «Горэнерго»", "ПАО «Ростелеком»", "ООО «Чистый дом»", "УФК (ФНС России), ЕНП", "ЧОП «Щит»"}
    assert not regular & NOT_REGULAR
    assert {r["name"] for r in MAIN["not_recurring"]} == {"ООО «Яндекс»", "ООО «ВетКлауд»", "АО «Роял Канин»", "ООО «Медтехсервис»"}
    rostelecom = next(s for s in MAIN["recurring"] if s["name"] == "ПАО «Ростелеком»")
    assert rostelecom["slots"][0]["day"] == 18 and not any(p["name"] == "ПАО «Ростелеком»" for d in MAIN["days"] for p in d["payments"])


def test_texts_contain_the_numbers():
    a = MAIN["alerts"][0]
    assert contains_amount(a["title"], HAND["shortfall"]) and contains_amount(a["text"], HAND["lowest"][1])
    assert contains_amount(a["suggestion"]["text"], 10_850_000) and "12 октября" in a["suggestion"]["text"]


# ---------------------------------------------------------------- obligations
def test_obligations_summary_equals_hand_values():
    loans = {x["kind"]: x for x in OBL["loans"]}
    assert loans["loan"]["remaining"] == HAND_OBL["loan_remaining"] and loans["lease"]["remaining"] == HAND_OBL["lease_remaining"]
    assert (OBL["debt_total"], OBL["monthly_payment"], OBL["amortization_month"]) == \
        (HAND_OBL["debt_total"], HAND_OBL["monthly_payment"], HAND_OBL["amortization_oct"])
    assert (loans["loan"]["paid_pct"], loans["lease"]["paid_pct"]) == (25.7, 83.3)
    assert (loans["loan"]["until"], loans["lease"]["until"]) == ("2028-10", "2027-03")


def test_interest_and_charges_by_a_decimal_recount():
    loan = next(o for o in DATA["obligations"] if o["kind"] == "loan")
    assert half_up(Decimal(HAND_OBL["loan_remaining"]) * loan["annual_rate_bp"] / 120_000) == HAND_OBL["interest_oct"]
    assert EXPECTED["charges_by_month"]["2026-10"]["total"] == HAND_OBL["charges_oct"] == EXPECTED["pnl_obligations_row"]["2026-10"]
    assert EXPECTED["charges_by_month"]["2026-09"]["total"] == HAND_OBL["charges_sep"]
    assert OBL["charges_month"]["total"] == HAND_OBL["charges_oct"]
    april = {c["obligation_id"]: c["amount"] for c in EXPECTED["charges_by_month"]["2026-04"]["items"]}
    assert april["S5-eq-autoclave"] == HAND_OBL["autoclave_last"] == 196_647
    for o in DATA["obligations"]:
        if o["kind"] == "equipment":
            assert half_up(Decimal(o["cost"]) / (o["life_years"] * 12)) == next(e["monthly"] for e in OBL["equipment"] if e["id"] == o["id"])


def test_loan_schedule_repays_the_principal_exactly():
    loan = next(o for o in DATA["obligations"] if o["kind"] == "loan")
    sched = EXPECTED["loan_schedule"]
    assert all(r["payment"] == r["interest"] + r["principal"] for r in sched)
    assert all(a["balance_after"] == b["balance_before"] for a, b in zip(sched, sched[1:]))
    assert sched[0]["balance_before"] == loan["principal"]
    oct_row = next(r for r in sched if r["month"] == "2026-10")
    assert oct_row["balance_before"] == HAND_OBL["loan_remaining"] and oct_row["date"] == "2026-10-08"


@pytest.mark.parametrize("month", DATA["charge_months"])
def test_charges_add_up(month):
    c = EXPECTED["charges_by_month"][month]
    assert sum(i["amount"] for i in c["items"]) == c["total"] == EXPECTED["pnl_obligations_row"][month]
