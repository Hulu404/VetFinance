"""Input rows of the stage 4 engines (payment calendar, obligations). Plain frozen dataclasses: no database, no network."""

import hashlib
from dataclasses import dataclass
from datetime import date

KIND_LOAN = "loan"
KIND_LEASE = "lease"
KIND_EQUIPMENT = "equipment"
NAME_KEY_PREFIX = "n-"
NAME_KEY_LENGTH = 12


def counterparty_key(inn: str | None, name: str) -> str:
    """Identity of a counterparty: the INN, or a key made of the name when the statement has no INN."""
    if inn:
        return inn
    digest = hashlib.sha256(name.strip().casefold().encode("utf-8")).hexdigest()
    return NAME_KEY_PREFIX + digest[:NAME_KEY_LENGTH]


@dataclass(frozen=True)
class ObligationInput:
    """Terms of a loan, a lease or a piece of equipment. Charges and payments are calculated from them.

    loan: `start_balance` (default `principal`) is the debt before the first payment of the schedule;
    lease: `start_balance` (default `payment x payments_total`) is what is left to pay before the first payment,
    `principal` the sum of all payments of the contract; equipment: cost, life, in-service date.
    `effective_from` (first of a month): no charges before it; `closed_from`: no charges and payments from it on.
    """

    id: str
    kind: str  # KIND_*
    name: str
    lender: str | None = None
    counterparty_inn: str | None = None
    principal: int | None = None
    annual_rate_bp: int | None = None
    payment: int | None = None
    payment_day: int | None = None
    first_payment_date: date | None = None
    payments_total: int | None = None
    cost: int | None = None
    life_years: int | None = None
    in_service_date: date | None = None
    start_balance: int | None = None
    effective_from: date | None = None
    closed_from: date | None = None


@dataclass(frozen=True)
class PlannedPaymentInput:
    """A one-off payment entered by hand (source `manual`)."""

    id: str
    date: date
    name: str
    amount: int
    max_deferral_days: int = 0
    category: str | None = None


@dataclass(frozen=True)
class CounterpartyTermsInput:
    """Deferral a counterparty allows. `inn` holds the key of `counterparty_key` (INN or a name key)."""

    inn: str
    name: str
    max_deferral_days: int = 0


@dataclass(frozen=True)
class PaymentMoveInput:
    """One payment of the window moved to another day (preview of a suggestion)."""

    name: str
    source: str
    from_date: date
    to_date: date
    payment_id: str | None = None
