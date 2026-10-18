"""Shared helpers for the set06 golden tests (stage 5: price list, service cost, efficiency).

Loads data.json / expected.json and builds engine inputs. Contains NO business logic: every expected number comes from
expected.json (computed by tools/compute_expected_set06.py, rules in set06/README.md).

Interface under test is the tester's proposal (docs/handoff.md, "tester -> backend-developer (этап 5)"):
    engine.efficiency.compute_efficiency(visits, sales, doctors, rooms, room_bookings, pnl_month, avg_visit_minutes, month, as_of)
        -> {"load_by", "status", "partial_reasons", "visits", "avg_check", "load_pct", "busy_hours", "available_hours",
            "hour_cost", "hour_margin", "rooms": [...], "doctors": [...]}
    engine.pricing.compute_price_list(sales, manual_services, service_settings, techcards, stock_items, stock_batches, pnl_month, hour_cost,
                                      month, as_of, sort="margin")
        -> {"counts": {"all", "loss", "no_recipe"}, "items": [item, ...]}                (worst margin first)
    engine.pricing.compute_service_cost(<same arguments>, service_id) -> card of GET /v1/services/{id}/cost
`hour_cost` (kopecks or None) is the output of compute_efficiency; the price tests pass the GOLDEN hour cost of the case, so the
two engines are tested independently. Functions are called with the keyword arguments they accept (inspect.signature); input
classes are built with the fields they have. Results may hold Figures (dicts with `value`) or plain numbers: `v()` reads both.
Tests skip while a module, a function or an input class is missing. Tester-only switch: VF_ENGINE_OVERRIDE=<dir> puts <dir>
(a folder with an `engine` package) in front of backend/.
"""
import dataclasses
import importlib
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from set05_support import call, engine_function, plain, v  # noqa: F401  (generic helpers shared with set05)

BASE = Path(__file__).resolve().parent / "set06"
DATA = json.loads((BASE / "data.json").read_text(encoding="utf-8"))
EXPECTED = json.loads((BASE / "expected.json").read_text(encoding="utf-8"))
D = date.fromisoformat
AS_OF = D(DATA["as_of"])
MONTH = DATA["month"]
CASE_KEYS = [c["key"] for c in DATA["cases"]]
SERVICE_CASES = [c["key"] for c in DATA["cases"] if not c.get("efficiency_only")]      # the price list is checked in these
CASES = {c["key"]: c for c in DATA["cases"]}
CLASS_MODULES = ("engine.pricing_inputs", "engine.efficiency_inputs", "engine.pricing", "engine.efficiency",
                 "engine.dashboard_inputs", "engine.reports_inputs", "engine.planning_inputs")
PART_KEYS = ["doctor_pay", "drugs", "anesthesia", "supplies", "acquiring", "fixed", "taxes"]


def find_class(class_name):
    for module in CLASS_MODULES:
        try:
            cls = getattr(importlib.import_module(module), class_name, None)
        except ImportError:
            continue
        if cls is not None:
            return cls
    return None


def build(class_name, required=(), **kwargs):
    cls = find_class(class_name)
    if cls is None:
        pytest.skip(f"input class {class_name} is not defined yet; interface proposed in docs/handoff.md")
    names = {f.name for f in dataclasses.fields(cls)}
    lacking = [r for r in required if r not in names]
    if lacking:
        pytest.skip(f"{class_name} has no fields {lacking} yet; proposed in docs/handoff.md")
    return cls(**{k: x for k, x in kwargs.items() if k in names})


def _slots(schedule):
    return tuple(build("ScheduleSlotInput", weekday=s["weekday"], from_min=s["from_min"], to_min=s["to_min"]) for s in schedule)


def inputs_for(case_key="main") -> dict:
    """All inputs of the stage 5 engines as keyword arguments for the case (schedules / hours dropped as the case says)."""
    case = CASES[case_key]
    sales = [build("SaleInput", required=("id",), id=s["id"], date=D(s["date"]), status=s["status"], amount=s["amount"],
                   lines=tuple(build("SaleLineInput", required=("service_id", "qty", "price"), kind=ln["kind"],
                                     amount=ln["amount"], service_id=ln.get("service_id"), name=ln["name"], qty=ln["qty"],
                                     price=ln["price"], doctor_id=ln.get("doctor_id")) for ln in s["lines"]))
             for s in DATA["sales"]]
    pnl = DATA["pnl_month"]
    no_expenses = bool(case.get("no_expenses"))          # a month without a statement: no expenses in the P&L
    pnl_month = build("PnlMonthInput", month=pnl["month"], revenue=pnl["revenue"], variable_total=pnl["variable_total"],
                      marginal_profit=pnl["marginal_profit"], doctor_percent_payouts=pnl["doctor_percent_payouts"],
                      acquiring_fee=pnl["acquiring_fee"], taxes=pnl["taxes"],
                      fixed_lines=tuple(build("PnlLineInput", name=x["name"], amount=x["amount"], kind=x["kind"])
                                        for x in ([] if no_expenses else pnl["fixed_lines"])),
                      obligation_lines=tuple(build("PnlLineInput", name=x["name"], amount=x["amount"], kind="obligations")
                                             for x in ([] if no_expenses else pnl["obligation_lines"])))
    doctors = [build("DoctorInput", id=d["id"], code=d["code"], name=d["name"],
                     hours_per_week=None if d["id"] in case["drop_doctor_hours"] else Decimal(d["hours_per_week"]))
               for d in DATA["doctors"]]
    rooms = [build("RoomInput", id=r["id"], name=r["name"],
                   schedule=None if r["id"] in case["drop_room_schedules"] else _slots(r["schedule"])) for r in DATA["rooms"]]
    bookings = [build("RoomBookingInput", date=D(b["date"]), room_id=b["room_id"], minutes=b["minutes"])
                for b in DATA["room_bookings"]]
    settings = [build("ServiceSettingInput", service_id=s["service_id"], name=s["name"], group=s["group"], minutes=s["minutes"],
                      doctor_pct_bp=s["doctor_pct_bp"]) for s in DATA["service_settings"]]
    techcards = [build("TechcardInput", service_id=t["service_id"],
                       lines=tuple(build("TechcardLineInput", item_id=ln["item_id"], qty=Decimal(ln["qty"]), part=ln["part"])
                                   for ln in t["lines"])) for t in DATA["techcards"]]
    manual = [build("ManualServiceInput", id=m["id"], name=m["name"], price=m["price"]) for m in DATA["manual_services"]]
    items = [build("StockItemInput", id=i["id"], name=i["name"], unit=i["unit"], last_movement=None) for i in DATA["stock_items"]]
    batches = [build("StockBatchInput", required=("received_on",), id=b["id"], item_id=b["item_id"], qty=Decimal(b["qty"]),
                     unit_cost=b["unit_cost"], received_on=D(b["received_on"]) if b["received_on"] else None,
                     expires_on=D(b["expires_on"]) if b["expires_on"] else None) for b in DATA["stock_batches"]]
    visits = [build("VisitInput", required=("doctor_id",), date=D(x["date"]), doctor=x["doctor_id"], doctor_id=x["doctor_id"])
              for x in DATA["visits"]]
    return {"sales": sales, "doctors": doctors, "rooms": rooms, "room_bookings": bookings, "service_settings": settings,
            "manual_services": manual, "techcards": techcards, "stock_items": items, "stock_batches": batches, "visits": visits, "pnl_month": pnl_month,
            "avg_visit_minutes": DATA["clinic"]["avg_visit_minutes"], "month": MONTH, "as_of": AS_OF,
            "hour_cost": EXPECTED["cases"][case_key]["hour_cost"]}


def run_price(case_key="main", fn=None, inputs=None, **extra):
    fn = fn or engine_function("engine.pricing", "compute_price_list")
    return plain(call(fn, **(inputs or inputs_for(case_key)), **extra))


def run_efficiency(case_key="main", fn=None, inputs=None, **extra):
    fn = fn or engine_function("engine.efficiency", "compute_efficiency")
    return plain(call(fn, **(inputs or inputs_for(case_key)), **extra))


# ---------------------------------------------------------------- normalisation of the engine output
def parts_of(item) -> dict:
    """{part key: kopecks | None} for the seven parts, from `parts` as a list [{key, amount}] (contract) or a dict."""
    parts = item["parts"]
    if isinstance(parts, dict):
        return {k: (v(x) if x is not None else None) for k, x in parts.items() if k in PART_KEYS}
    return {p["key"]: (v(p["amount"]) if p.get("amount") is not None else None) for p in parts if p["key"] in PART_KEYS}


def shares_of(item) -> dict:
    parts = item["parts"]
    if isinstance(parts, dict):
        return {k: x.get("share_pct") for k, x in parts.items() if isinstance(x, dict) and k in PART_KEYS}
    return {p["key"]: (v(p["share_pct"]) if p.get("share_pct") is not None else None) for p in parts if p["key"] in PART_KEYS}


def by_id(items) -> dict:
    return {s["id"]: s for s in items}


def rows_by_id(rows) -> dict:
    return {r.get("id") or r["name"]: r for r in rows}


def hour_parts(result) -> dict:
    """{key: value} of `hour_cost_parts` when its items carry a `key` (designer: hours, busy_hours, fixed, obligations)."""
    parts = result.get("hour_cost_parts") or []
    if not parts or not isinstance(parts[0], dict) or "key" not in parts[0]:
        pytest.skip("hour_cost_parts items have no `key` yet (proposal in docs/handoff.md: {key, label, figure})")
    return {p["key"]: v(p.get("figure", p)) for p in parts}


def figure_lines(fig) -> list:
    """Values of the breakdown of a Figure (the two lines of the hour cost: fixed per hour, obligations per hour)."""
    if not isinstance(fig, dict) or not fig.get("breakdown"):
        pytest.skip("the engine returns the hour cost without a breakdown (a plain number)")
    return [b["value"] for b in fig["breakdown"]]
