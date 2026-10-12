"""Account balance as of a date.

Rules:
- Balance of an account = opening_balance + sum of amounts of its transactions with
  opening_date <= date <= as_of.
- Transactions with status "duplicate" are excluded. Status "check" is included.
- Transactions after as_of or before the account's opening_date are excluded.
- Amounts are signed (income > 0, expense < 0); a transfer carries its own sign per account.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from engine.figure import Figure, FigureItem, ordered_sources

KIND_BANK = "bank"
KIND_CASH = "cash"
STATUS_DUPLICATE = "duplicate"
SOURCE_OPENING = "manual"


@dataclass(frozen=True)
class AccountInput:
    id: str
    name: str
    kind: str  # "bank" | "cash"
    opening_balance: int
    opening_date: date


@dataclass(frozen=True)
class TransactionInput:
    account_id: str
    date: date
    amount: int
    status: str  # "ok" | "check" | "duplicate"
    source: str  # "bank" | "vetmanager" | "bot" | "manual"
    kind: str = ""  # "in" | "out" | "transfer"; empty when the caller does not need it
    category: str | None = None  # category name, None: no category


@dataclass(frozen=True)
class BalanceResult:
    as_of: date
    total: Figure
    bank: Figure
    cash: Figure


def account_balance(
    account: AccountInput, transactions: Iterable[TransactionInput], as_of: date
) -> tuple[int, set[str]]:
    """Balance of one account and the set of sources that contributed to it."""
    value = account.opening_balance
    sources: set[str] = set()
    for tx in transactions:
        if tx.account_id != account.id or tx.status == STATUS_DUPLICATE:
            continue
        if tx.date > as_of or tx.date < account.opening_date:
            continue
        value += tx.amount
        sources.add(tx.source)
    return value, sources


def _figure(
    title: str,
    as_of: date,
    parts: list[tuple[AccountInput, int, set[str]]],
) -> Figure:
    sources: set[str] = set()
    for _, _, src in parts:
        sources |= src
    total = sum(value for _, value, _ in parts)
    note = (
        f"{title} на {as_of.isoformat()}: остаток на начало плюс операции без дублей, "
        f"счетов: {len(parts)}."
    )
    return Figure(
        value=total,
        unit="rub",
        breakdown=tuple(FigureItem(label=a.name, value=v) for a, v, _ in parts),
        source=ordered_sources(sources) or (SOURCE_OPENING,),
        note=note,
    )


def compute_balance(
    accounts: Iterable[AccountInput],
    transactions: Iterable[TransactionInput],
    as_of: date,
) -> BalanceResult:
    """Total, bank and cash balances as of `as_of` (inclusive)."""
    tx_list = list(transactions)
    parts = [
        (a, *account_balance(a, tx_list, as_of))
        for a in sorted(accounts, key=lambda a: (a.name, a.id))
    ]
    bank = [p for p in parts if p[0].kind == KIND_BANK]
    cash = [p for p in parts if p[0].kind == KIND_CASH]
    return BalanceResult(
        as_of=as_of,
        total=_figure("Остаток на всех счетах", as_of, parts),
        bank=_figure("Остаток на расчётных счетах", as_of, bank),
        cash=_figure("Остаток в кассе", as_of, cash),
    )
