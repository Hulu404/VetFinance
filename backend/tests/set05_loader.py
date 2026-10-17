"""Golden set 5 (tests/golden/set05, read only) loaded into the in-memory repository."""

import json
from datetime import date
from pathlib import Path
from typing import Any

from app.rows import ClinicRow
from engine.planning_inputs import CounterpartyTermsInput, ObligationInput, PlannedPaymentInput
from tests.memory_repo import MemoryRepo

GOLDEN = Path(__file__).resolve().parents[2] / "tests" / "golden" / "set05"
DATA: dict[str, Any] = json.loads((GOLDEN / "data.json").read_text(encoding="utf-8"))
EXPECTED: dict[str, Any] = json.loads((GOLDEN / "expected.json").read_text(encoding="utf-8"))
D = date.fromisoformat


def _day(value: str | None) -> date | None:
    return D(value) if value else None


def load_set05(safe_balance: int | None = None) -> MemoryRepo:
    clinic = DATA["clinic"]
    safe = clinic["safe_balance"] if safe_balance is None else safe_balance
    repo = MemoryRepo(ClinicRow("f", clinic["name"], None, None, clinic["timezone"], safe))
    repo.add_connections()
    for a in DATA["accounts"]:
        repo.add_account(
            id=a["id"],
            name=a["name"],
            kind=a["type"],
            opening_balance=a["opening_balance"],
            opening_date=D(a["opening_date"]),
        )
    ids = {c["name"]: repo.add_category(c["name"], c["type"]).id for c in DATA["categories"]}
    for t in DATA["transactions"]:
        repo.add_tx(
            t["account_id"],
            D(t["date"]),
            t["amount"],
            source=t["source"],
            status=t["status"],
            kind=t["kind"],
            category_id=ids.get(t["category"]),
            inn=t["counterparty_inn"],
            counterparty_name=t["counterparty_name"],
        )
    repo.obligations = [
        ObligationInput(
            id=o["id"],
            kind=o["kind"],
            name=o["name"],
            lender=o.get("lender"),
            counterparty_inn=o.get("counterparty_inn"),
            principal=o.get("principal"),
            annual_rate_bp=o.get("annual_rate_bp"),
            payment=o.get("payment"),
            payment_day=o.get("payment_day"),
            first_payment_date=_day(o.get("first_payment_date")),
            payments_total=o.get("payments_total"),
            cost=o.get("cost"),
            life_years=o.get("life_years"),
            in_service_date=_day(o.get("in_service_date")),
        )
        for o in DATA["obligations"]
    ]
    repo.planned = [
        PlannedPaymentInput(p["id"], D(p["date"]), p["name"], p["amount"], p["max_deferral_days"])
        for p in DATA["planned_payments"]
    ]
    repo.terms = {
        c["inn"]: CounterpartyTermsInput(c["inn"], c["name"], c["max_deferral_days"])
        for c in DATA["counterparties"]
    }
    return repo
