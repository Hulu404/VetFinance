"""Golden set 6 (tests/golden/set06, read only) loaded into the in-memory repository: clinic G, stage 5.

The totals of the September P&L (tests/golden/set06/README.md) are produced by bank operations, card payments and
obligation charges that give the same numbers, so that the whole chain (P&L -> hour cost -> price) can be checked.
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.rows import ClinicRow
from engine.efficiency_inputs import RoomBookingInput, RoomInput, ScheduleSlotInput
from engine.pricing_inputs import StockBatchInput, StockItemInput, TechcardLineInput
from engine.reports_inputs import ObligationChargeInput
from engine.vetmanager import Payment, Sale, SaleLine, Visit
from tests.memory_repo import MemoryRepo

GOLDEN = Path(__file__).resolve().parents[2] / "tests" / "golden" / "set06"
DATA: dict[str, Any] = json.loads((GOLDEN / "data.json").read_text(encoding="utf-8"))
EXPECTED: dict[str, Any] = json.loads((GOLDEN / "expected.json").read_text(encoding="utf-8"))
D = date.fromisoformat
CARD_DAYS = 25
CARD_PER_DAY = (
    2_000_000  # 25 x 20 000 rub at 1.9% = 9 500 rub of commission, as the golden P&L says
)


def _day(value: str | None) -> date | None:
    return D(value) if value else None


def _categories(repo: MemoryRepo) -> dict[str, str]:
    flags: list[tuple[str, str, dict[str, bool]]] = [
        ("Проценты врачам", "variable", {"doctor_percent": True}),
        ("Препараты и закупки", "variable", {}),
        ("Налоги", "tax", {}),
        ("Оклады сотрудников", "fixed", {"payroll": True}),
        ("Аренда и коммуналка", "fixed", {}),
        ("Маркетинг", "fixed", {}),
        ("Связь и прочее", "fixed", {}),
        ("Расходные материалы", "fixed", {"in_service_recipes": True}),
    ]
    return {name: repo.add_category(name, kind, **opts).id for name, kind, opts in flags}


def _pnl(repo: MemoryRepo) -> None:
    """Operations of September that give the totals of data.json -> pnl_month."""
    pnl = DATA["pnl_month"]
    ids = _categories(repo)
    repo.add_account(
        id="g-bank",
        name="Расчётный счёт",
        kind="bank",
        opening_balance=100_000_000,
        opening_date=D("2026-06-01"),
    )
    fixed = {x["kind"]: x for x in pnl["fixed_lines"]}
    others = pnl["variable_total"] - pnl["acquiring_fee"] - pnl["doctor_percent_payouts"]
    rows = [
        ("Проценты врачам", pnl["doctor_percent_payouts"]), ("Препараты и закупки", others), ("Налоги", pnl["taxes"]),
        ("Оклады сотрудников", fixed["payroll"]["amount"]), ("Аренда и коммуналка", fixed["rent"]["amount"]),
        ("Маркетинг", fixed["marketing"]["amount"]), ("Связь и прочее", fixed["other"]["amount"]),
        ("Расходные материалы", fixed["materials"]["amount"]),
    ]  # fmt: skip
    for name, amount in rows:
        repo.add_tx("g-bank", D("2026-09-15"), -amount, category_id=ids[name], kind="out")
    for number in range(CARD_DAYS):
        day = D("2026-09-01").replace(day=number + 1)
        payment = Payment(f"card-{number}", day, CARD_PER_DAY, "card", None)
        repo.payments[payment.external_id] = (payment, None)
    kinds = ("amortization", "lease", "loan_interest")
    repo.charges = [
        ObligationChargeInput("2026-09", f"obl-{i}", x["name"], kinds[i], x["amount"])
        for i, x in enumerate(pnl["obligation_lines"])
    ]


def _sales(repo: MemoryRepo) -> None:
    for d in DATA["doctors"]:
        repo.doctors[d["id"]] = (d["id"], d["code"], d["name"])
        repo.hours[d["id"]] = None if d["hours_per_week"] is None else Decimal(d["hours_per_week"])
    for v in DATA["visits"]:
        repo.visits[v["id"]] = (D(v["date"]), v["doctor_id"])
    for s in DATA["sales"]:
        lines = tuple(
            SaleLine(x["kind"], x["amount"], x.get("service_id"), x["name"] if x.get("service_id") else "",
                     Decimal(x["qty"]), x["price"])
            for x in s["lines"]
        )  # fmt: skip
        repo.sales[s["id"]] = Sale(s["id"], D(s["date"]), s["status"], s["amount"], lines)


def _services(repo: MemoryRepo) -> None:
    from app.rows import ServiceRecord

    settings = {s["service_id"]: s for s in DATA["service_settings"]}
    names: dict[str, str] = {}
    for sale in DATA["sales"]:
        for ln in sale["lines"]:
            if ln.get("service_id"):
                names[ln["service_id"]] = ln["name"]
    manual = {m["id"] for m in DATA["manual_services"]}
    for sid in sorted(set(names) | {k for k in settings if k not in manual}):
        st = settings.get(sid)
        repo.services.append(
            ServiceRecord(
                sid,
                "vetmanager",
                sid,
                st["name"] if st else names[sid],
                st["group"] if st else None,
                None,
            )
        )
    for m in DATA["manual_services"]:
        st = settings.get(m["id"])
        repo.services.append(
            ServiceRecord(
                m["id"], "manual", None, m["name"], st["group"] if st else None, m["price"]
            )
        )
    for sid, st in settings.items():
        repo.service_settings[sid] = (st["minutes"], st["doctor_pct_bp"])
    for card in DATA["techcards"]:
        repo.recipes[card["service_id"]] = [
            TechcardLineInput(x["item_id"], Decimal(x["qty"]), x["part"]) for x in card["lines"]
        ]


def _stock_and_rooms(repo: MemoryRepo) -> None:
    repo.pricing_items = [
        StockItemInput(i["id"], i["name"], i["unit"]) for i in DATA["stock_items"]
    ]
    repo.pricing_batches = [
        StockBatchInput(
            b["id"],
            b["item_id"],
            Decimal(b["qty"]),
            b["unit_cost"],
            _day(b["received_on"]),
            _day(b["expires_on"]),
        )
        for b in DATA["stock_batches"]
    ]
    repo.rooms = [
        RoomInput(
            r["id"],
            r["name"],
            tuple(
                ScheduleSlotInput(s["weekday"], s["from_min"], s["to_min"]) for s in r["schedule"]
            ),
        )
        for r in DATA["rooms"]
    ]
    repo.room_bookings = [
        RoomBookingInput(D(b["date"]), b["room_id"], b["minutes"]) for b in DATA["room_bookings"]
    ]


def load_set06() -> MemoryRepo:
    clinic = DATA["clinic"]
    repo = MemoryRepo(ClinicRow("g", clinic["name"], None, None, clinic["timezone"], 0))
    repo.add_connections()
    repo.avg_visit_minutes = clinic["avg_visit_minutes"]
    _pnl(repo)
    _sales(repo)
    _services(repo)
    _stock_and_rooms(repo)
    return repo


__all__ = ["DATA", "EXPECTED", "Visit", "load_set06"]
