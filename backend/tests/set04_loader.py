"""Golden set 4 (tests/golden/set04, read only) loaded into the in-memory repository."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.rows import ClinicRow
from engine.reports_inputs import (
    BenchmarkInput,
    ConsumptionInput,
    ObligationChargeInput,
    StockBatchInput,
    StockItemInput,
    WriteoffInput,
)
from engine.vetmanager import Payment, Sale, SaleLine
from tests.memory_repo import MemoryRepo

GOLDEN = Path(__file__).resolve().parents[2] / "tests" / "golden" / "set04"
DATA: dict[str, Any] = json.loads((GOLDEN / "data.json").read_text(encoding="utf-8"))
EXPECTED: dict[str, Any] = json.loads((GOLDEN / "expected.json").read_text(encoding="utf-8"))
D = date.fromisoformat


def _dec(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def load_set04() -> MemoryRepo:
    clinic = DATA["clinic"]
    repo = MemoryRepo(ClinicRow("e", clinic["name"], None, None, clinic["timezone"], 0))
    repo.add_connections()
    repo.acquiring_rate_bp = clinic["acquiring_rate_bp"]
    covered = D(DATA["bank_covered_to"]) if DATA.get("bank_covered_to") else None
    for a in DATA["accounts"]:
        repo.add_account(
            id=a["id"],
            name=a["name"],
            kind=a["type"],
            opening_balance=a["opening_balance"],
            opening_date=D(a["opening_date"]),
            last_statement_to=covered if a["type"] == "bank" else None,
        )
    ids = {
        c["name"]: repo.add_category(
            c["name"],
            c["type"],
            norm_min_pct=c["norm_min_pct"],
            norm_max_pct=c["norm_max_pct"],
            norm_key=c["norm_key"],
            direction=c["direction"],
            payroll=c["payroll"],
        ).id
        for c in DATA["categories"]
    }
    for t in DATA["transactions"]:
        repo.add_tx(
            t["account_id"],
            D(t["date"]),
            t["amount"],
            source=t["source"],
            status=t["status"],
            kind=t["kind"],
            category_id=ids.get(t["category"]),
        )
    for s in DATA["sales"]:
        repo.sales[s["id"]] = Sale(
            s["id"],
            D(s["date"]),
            s["status"],
            s["amount"],
            tuple(SaleLine(ln["kind"], ln["amount"]) for ln in s["lines"]),
        )
    for p in DATA["payments"]:
        repo.payments[p["id"]] = (
            Payment(p["id"], D(p["date"]), p["amount"], p["method"], p["invoice_id"]),
            None,
        )
    load_reports_tables(repo)
    return repo


def load_reports_tables(repo: MemoryRepo) -> None:
    repo.charges = [
        ObligationChargeInput(c["month"], c["obligation_id"], c["name"], c["kind"], c["amount"])
        for c in DATA["obligation_charges"]
    ]
    repo.benchmarks = [
        BenchmarkInput(
            b["key"],
            b["label"],
            b["kind"],
            _dec(b["min_pct"]),
            _dec(b["max_pct"]),
            "industry",
            b["sort"],
        )
        for b in DATA["benchmarks"]
    ]
    stock = DATA["stock"]
    repo.stock_items = [
        StockItemInput(i["id"], i["name"], D(i["last_movement"])) for i in stock["items"]
    ]
    repo.stock_batches = [
        StockBatchInput(
            b["item_id"], b["qty"], b["unit_cost"], D(b["expires_on"]) if b["expires_on"] else None
        )
        for b in stock["batches"]
    ]
    repo.writeoffs = [
        WriteoffInput(D(w["date"]), w["item"], w["qty"], w["amount"], w["reason"])
        for w in stock["writeoffs"]
    ]
    repo.consumption = [ConsumptionInput(D(c["date"]), c["amount"]) for c in stock["consumption"]]
