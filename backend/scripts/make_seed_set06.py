"""Generate the idempotent, transactional seed of clinic G «Ясень» from golden set 6 (stage 5).

Requires all migrations through 20261018100000_stage5_pricing. Apply only to a test database. The synthetic user
test-g@vetfinance.test must already exist to link the clinic to a login. The totals of the September P&L are produced
by bank operations, card payments and frozen obligation charges that give the same numbers as data.json -> pnl_month
(see tests/set06_loader.py, which does the same in memory). No shared data and no other clinic is modified.
"""

import json
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "tests/golden/set06/data.json"
OUT = ROOT / "supabase/seed_set06.sql"
NS = uuid.UUID("5e0d5a3c-7c1f-4c0e-9b52-0a5f1d3e7a06")
EMAIL = "test-g@vetfinance.test"
CARD_DAYS, CARD_PER_DAY = 25, 2_000_000
CATEGORIES = (
    ("Проценты врачам", "variable", {"doctor_percent": True}),
    ("Препараты и закупки", "variable", {}),
    ("Налоги", "tax", {}),
    ("Оклады сотрудников", "fixed", {"payroll": True}),
    ("Аренда и коммуналка", "fixed", {}),
    ("Маркетинг", "fixed", {}),
    ("Связь и прочее", "fixed", {}),
    ("Расходные материалы", "fixed", {"in_service_recipes": True}),
)  # fmt: skip
OBLIGATIONS = (("amortization", "equipment"), ("lease", "lease"), ("loan_interest", "loan"))


def uid(kind: str, key: str) -> str:
    return str(uuid.uuid5(NS, f"{kind}:{key}"))


def q(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


class Sql:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def insert(self, table: str, conflict: str = "(id)", **values: object) -> None:
        self.lines.append(
            f"insert into public.{table} ({', '.join(values)}) values "
            f"({', '.join(q(v) for v in values.values())}) on conflict {conflict} do nothing;"
        )


def operations(sql: Sql, data: dict[str, Any], clinic: str) -> None:
    pnl = data["pnl_month"]
    sql.insert(
        "accounts", id=uid("account", "bank"), clinic_id=clinic, name="Расчётный счёт", kind="bank",
        opening_balance=100_000_000, opening_date="2026-06-01", last_statement_to="2026-09-30",
    )  # fmt: skip
    fixed = {x["kind"]: x["amount"] for x in pnl["fixed_lines"]}
    others = pnl["variable_total"] - pnl["acquiring_fee"] - pnl["doctor_percent_payouts"]
    amounts = [pnl["doctor_percent_payouts"], others, pnl["taxes"], fixed["payroll"], fixed["rent"],
               fixed["marketing"], fixed["other"], fixed["materials"]]  # fmt: skip
    for (name, kind, flags), amount in zip(CATEGORIES, amounts, strict=True):
        sql.insert(
            "categories", id=uid("category", name), clinic_id=clinic, name=name, type=kind, **flags
        )
        sql.insert(
            "transactions", id=uid("tx", name), clinic_id=clinic, account_id=uid("account", "bank"),
            date="2026-09-15", description=name, amount=-amount, kind="out", source="bank",
            external_id=f"S6-{name}", status="ok", category_id=uid("category", name),
            counterparty_inn="", counterparty_name="",
        )  # fmt: skip
    for n in range(CARD_DAYS):
        sql.insert(
            "payments", conflict="(clinic_id, external_id)", clinic_id=clinic, external_id=f"S6-card-{n}",
            date=f"2026-09-{n + 1:02d}", amount=CARD_PER_DAY, method="card", invoice_external_id=None,
        )  # fmt: skip
    for (kind, ob_kind), line in zip(OBLIGATIONS, pnl["obligation_lines"], strict=True):
        sql.insert(
            "obligations",
            id=uid("obligation", kind),
            clinic_id=clinic,
            code=f"S6-{kind}",
            name=line["name"],
            kind=ob_kind,
        )
        sql.insert(
            "obligation_charges", conflict="(clinic_id, obligation_id, month, kind)", id=uid("charge", kind),
            clinic_id=clinic, obligation_id=uid("obligation", kind), month="2026-09-01", kind=kind,
            amount=line["amount"], basis=line["name"],
        )  # fmt: skip


def visits_and_sales(sql: Sql, data: dict[str, Any], clinic: str) -> None:
    for d in data["doctors"]:
        sql.insert(
            "doctors", id=uid("doctor", d["id"]), clinic_id=clinic, external_id=d["id"], code=d["code"],
            name=d["name"], hours_per_week=d["hours_per_week"],
        )  # fmt: skip
    for v in data["visits"]:
        sql.insert(
            "visits", id=uid("visit", v["id"]), clinic_id=clinic, external_id=v["id"], date=v["date"],
            doctor_id=uid("doctor", v["doctor_id"]) if v["doctor_id"] else None,
        )  # fmt: skip
    for s in data["sales"]:
        lines = [_line(x) for x in s["lines"]]
        sql.insert(
            "sales", id=uid("sale", s["id"]), clinic_id=clinic, external_id=s["id"], date=s["date"],
            status=s["status"], amount=s["amount"], lines=json.dumps(lines, ensure_ascii=False),
        )  # fmt: skip


def _line(x: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"kind": x["kind"], "amount": x["amount"]}
    if x.get("service_id"):
        out.update(service_id=x["service_id"], name=x["name"], qty=str(x["qty"]), price=x["price"])
    return out


def services(sql: Sql, data: dict[str, Any], clinic: str) -> None:
    settings = {s["service_id"]: s for s in data["service_settings"]}
    manual = {m["id"]: m for m in data["manual_services"]}
    names: dict[str, str] = {}
    for sale in data["sales"]:
        for ln in sale["lines"]:
            if ln.get("service_id"):
                names[ln["service_id"]] = ln["name"]
    for sid in sorted(set(names) | {k for k in settings if k not in manual}):
        st = settings.get(sid)
        sql.insert(
            "services", id=uid("service", sid), clinic_id=clinic, source="vetmanager", external_id=sid,
            name=st["name"] if st else names[sid], group_name=st["group"] if st else None,
        )  # fmt: skip
    for m in manual.values():
        st = settings.get(m["id"])
        sql.insert(
            "services", id=uid("service", m["id"]), clinic_id=clinic, source="manual", name=m["name"].strip(),
            group_name=st["group"] if st else None, manual_price=m["price"],
        )  # fmt: skip
    for sid, st in settings.items():
        sql.insert(
            "service_settings", conflict="(service_id)", service_id=uid("service", sid), clinic_id=clinic,
            minutes=st["minutes"], doctor_pct_bp=st["doctor_pct_bp"],
        )  # fmt: skip
    for card in data["techcards"]:
        sid = card["service_id"]
        sql.insert(
            "techcards", conflict="(service_id)", service_id=uid("service", sid), clinic_id=clinic
        )
        for n, ln in enumerate(card["lines"]):
            sql.insert(
                "techcard_lines", id=uid("tcl", f"{sid}:{ln['item_id']}"), clinic_id=clinic,
                service_id=uid("service", sid), item_id=uid("item", ln["item_id"]), part=ln["part"],
                qty=ln["qty"], sort_order=n,
            )  # fmt: skip


def stock_and_rooms(sql: Sql, data: dict[str, Any], clinic: str) -> None:
    for i in data["stock_items"]:
        sql.insert(
            "stock_items", id=uid("item", i["id"]), clinic_id=clinic, external_id=i["id"], name=i["name"], unit=i["unit"]
        )  # fmt: skip
    for b in data["stock_batches"]:
        sql.insert(
            "stock_batches", id=uid("batch", b["id"]), clinic_id=clinic, external_id=b["id"],
            item_id=uid("item", b["item_id"]), qty=b["qty"], unit_cost=b["unit_cost"],
            expires_on=b["expires_on"], received_on=b["received_on"],
        )  # fmt: skip
    for r in data["rooms"]:
        sql.insert(
            "rooms",
            id=uid("room", r["id"]),
            clinic_id=clinic,
            external_id=r["id"],
            name=r["name"],
            has_schedule=True,
        )
        for n, s in enumerate(r["schedule"]):
            sql.insert(
                "room_schedule_slots", id=uid("slot", f"{r['id']}:{n}"), clinic_id=clinic, room_id=uid("room", r["id"]),
                weekday=s["weekday"], from_min=s["from_min"], to_min=s["to_min"],
            )  # fmt: skip
    for n, b in enumerate(data["room_bookings"]):
        sql.insert(
            "room_bookings", conflict="(clinic_id, external_id)", clinic_id=clinic, external_id=f"S6-b{n}",
            date=b["date"], room_id=uid("room", b["room_id"]), minutes=b["minutes"],
        )  # fmt: skip


def generate(data: dict[str, Any]) -> str:
    clinic = uid("clinic", "G")
    sql = Sql()
    sql.lines = [
        "-- GENERATED by backend/scripts/make_seed_set06.py from tests/golden/set06/data.json",
        "-- Synthetic clinic G. Requires migration 20261018100000_stage5_pricing.",
        "-- Existing rows are preserved.",
        "begin;",
    ]
    sql.insert(
        "clinics", id=clinic, name=data["clinic"]["name"], timezone=data["clinic"]["timezone"], safe_balance=0,
        avg_visit_minutes=data["clinic"]["avg_visit_minutes"],
    )  # fmt: skip
    operations(sql, data, clinic)
    visits_and_sales(sql, data, clinic)
    stock_and_rooms(sql, data, clinic)  # stock items before the techcard lines that refer to them
    services(sql, data, clinic)
    sql.lines.extend(
        [
            "insert into public.memberships (clinic_id, user_id) "
            f"select {q(clinic)}, u.id from auth.users u where u.email = {q(EMAIL)} "
            "on conflict (user_id, clinic_id) do nothing;",
            "commit;",
        ]
    )
    return "\n".join(sql.lines) + "\n"


if __name__ == "__main__":
    OUT.write_text(generate(json.loads(DATA.read_text(encoding="utf-8"))), encoding="utf-8")
    print(f"wrote {OUT}")
