from datetime import date

from engine.balance import AccountInput, TransactionInput, compute_balance

BANK = AccountInput("a1", "Расчётный счёт", "bank", 10_000_000, date(2026, 9, 1))
CASH = AccountInput("a2", "Касса", "cash", 500_000, date(2026, 9, 1))
AS_OF = date(2026, 9, 10)


def tx(
    account: str, day: int, amount: int, status: str = "ok", source: str = "bank"
) -> TransactionInput:
    return TransactionInput(account, date(2026, 9, day), amount, status, source)


def test_opening_balance_without_transactions() -> None:
    r = compute_balance([BANK, CASH], [], AS_OF)
    assert r.total.value == 10_500_000
    assert r.bank.value == 10_000_000
    assert r.cash.value == 500_000
    assert r.total.source == ("manual",)


def test_sums_signed_amounts_per_account() -> None:
    txs = [
        tx("a1", 2, 3_000_000),
        tx("a1", 5, -1_250_000),
        tx("a2", 3, 100_000, source="vetmanager"),
    ]
    r = compute_balance([BANK, CASH], txs, AS_OF)
    assert r.bank.value == 11_750_000
    assert r.cash.value == 600_000
    assert r.total.value == 12_350_000
    assert [(i.label, i.value) for i in r.total.breakdown] == [
        ("Касса", 600_000),
        ("Расчётный счёт", 11_750_000),
    ]
    assert r.total.source == ("bank", "vetmanager")
    assert r.bank.source == ("bank",)


def test_duplicates_excluded_check_included() -> None:
    txs = [
        tx("a1", 2, 1_000),
        tx("a1", 2, 1_000, status="duplicate"),
        tx("a1", 3, 500, status="check"),
    ]
    assert compute_balance([BANK], txs, AS_OF).total.value == 10_001_500


def test_future_and_pre_opening_excluded_boundary_inclusive() -> None:
    txs = [
        tx("a1", 10, 100),  # on as_of: included
        tx("a1", 11, 999_999),  # after as_of: excluded
        TransactionInput("a1", date(2026, 8, 31), 777, "ok", "bank"),  # before opening_date
        tx("a1", 1, 10),  # on opening_date: included
    ]
    assert compute_balance([BANK], txs, AS_OF).total.value == 10_000_110


def test_foreign_account_ignored_and_empty_kind() -> None:
    r = compute_balance([BANK], [tx("zzz", 2, 5)], AS_OF)
    assert r.total.value == 10_000_000
    assert r.cash.value == 0
    assert r.cash.breakdown == ()


def test_deterministic_and_note() -> None:
    txs = [tx("a1", 2, 5)]
    assert compute_balance([BANK, CASH], txs, AS_OF) == compute_balance([CASH, BANK], txs, AS_OF)
    assert "2026-09-10" in compute_balance([BANK], [], AS_OF).total.note


def test_manual_only_when_figure_has_no_included_transactions() -> None:
    # bank account has a bank transaction, cash account has none
    r = compute_balance([BANK, CASH], [tx("a1", 3, 1)], AS_OF)
    assert r.total.source == ("bank",)  # no "manual" just because one account is empty
    assert r.bank.source == ("bank",)
    assert r.cash.source == ("manual",)  # nothing included in this Figure
    assert compute_balance([BANK, CASH], [], AS_OF).total.source == ("manual",)
