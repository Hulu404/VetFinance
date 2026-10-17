"""Shared helpers for the set05 golden tests (stage 4: payment calendar and obligations).

Loads data.json / expected.json and builds engine inputs. Contains NO business logic: every expected number comes from
expected.json (computed by tools/compute_expected_set05.py).

Interface under test is the tester's proposal (docs/handoff.md, "tester -> backend-developer (этап 4)"):
    engine.obligations.compute_obligation_charges(obligations, month)                      -> [ObligationChargeInput]
    engine.obligations.compute_obligations(obligations, as_of)                             -> summary (GET /v1/obligations)
    engine.calendar.detect_recurring(transactions, categories, as_of, counterparties=())    -> [series]
    engine.calendar.income_profile(transactions, categories, as_of)                        -> 7 amounts, Monday first
    engine.calendar.compute_calendar(accounts, transactions, categories, obligations, planned_payments, counterparties,
                                     safe_balance, as_of, days=22, moves=())                -> calendar (GET /v1/calendar)
Functions are called with the keyword arguments they accept (inspect.signature); input classes are built with the fields
they have. Results may hold Figures (dicts / dataclasses with `value`) or plain ints: `v()` reads both. Tests skip while a
module, a function or an input class is missing.
Tester-only switch: VF_ENGINE_OVERRIDE=<dir> puts <dir> (a folder with an `engine` package) in front of backend/.
"""
import dataclasses
import importlib
import inspect
import json
import os
import re
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parent / "set05"
DATA = json.loads((BASE / "data.json").read_text(encoding="utf-8"))
EXPECTED = json.loads((BASE / "expected.json").read_text(encoding="utf-8"))
D = date.fromisoformat
AS_OF = D(DATA["as_of"])
CASES = {c["key"]: c for c in DATA["cases"]}
CLASS_MODULES = ("engine.calendar_inputs", "engine.planning_inputs", "engine.calendar", "engine.obligations",
                 "engine.reports_inputs", "engine.balance", "engine.dashboard_inputs")


def plain(obj):
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: plain(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if hasattr(obj, "model_dump"):
        return plain(obj.model_dump())
    if isinstance(obj, dict):
        return {k: plain(x) for k, x in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [plain(x) for x in obj]
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, date):
        return obj.isoformat()
    return obj


def v(x):
    """Value of a Figure or of a plain number."""
    return x["value"] if isinstance(x, dict) else x


def engine_function(module: str, name: str):
    override = os.environ.get("VF_ENGINE_OVERRIDE")
    if override:
        for m in [m for m in sys.modules if m == "engine" or m.startswith("engine.")]:
            del sys.modules[m]
        sys.path.insert(0, override)
    try:
        mod = importlib.import_module(module)
    except ImportError as exc:
        pytest.skip(f"{module} is not implemented yet ({exc}); interface proposed in docs/handoff.md")
    fn = getattr(mod, name, None)
    if fn is None:
        pytest.skip(f"{module}.{name} is not defined yet; interface proposed in docs/handoff.md")
    return fn


def call(fn, **kwargs):
    """Call fn with the keyword arguments it accepts; an argument it requires but we do not have is an error."""
    params = inspect.signature(fn).parameters
    accepted = {k: x for k, x in kwargs.items() if k in params}
    missing = [n for n, p in params.items() if p.default is inspect.Parameter.empty and n not in accepted
               and p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)]
    assert not missing, f"{fn.__name__} requires arguments the tests do not know: {missing}"
    return fn(**accepted)


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


def _opt_date(x):
    return D(x) if x else None


def transactions(with_counterparty=True, extra=(), since=None):
    """Operations of data.json plus `extra` rows (same keys as data.json) from the date `since` on."""
    req = ("counterparty_inn", "counterparty_name") if with_counterparty else ()
    rows = [t for t in list(DATA["transactions"]) + list(extra) if since is None or D(t["date"]) >= since]
    return [build("TransactionInput", required=req, account_id=t["account_id"], date=D(t["date"]), amount=t["amount"],
                  status=t["status"], source=t["source"], kind=t["kind"], category=t["category"],
                  counterparty_inn=t["counterparty_inn"], counterparty_name=t["counterparty_name"])
            for t in rows]


def accounts():
    return [build("AccountInput", id=a["id"], name=a["name"], kind=a["type"], opening_balance=a["opening_balance"],
                  opening_date=D(a["opening_date"])) for a in DATA["accounts"]]


def categories():
    return [build("CategoryInput", name=c["name"], type=c["type"]) for c in DATA["categories"]]


def closed_from_value(month: str):
    """`closed_from` in the form the input class expects: "YYYY-MM" for a str field, the first day of the month otherwise."""
    cls = find_class("ObligationInput")
    field = next((f for f in dataclasses.fields(cls) if f.name == "closed_from"), None) if cls else None
    if field is not None and "str" in str(field.type) and "date" not in str(field.type):
        return month
    return month_arg(month)


def obligations(closed=None):
    """ObligationInput list; `closed` = {obligation id: "YYYY-MM"} closes those obligations from that month (needs `closed_from`)."""
    closed = closed or {}
    extra = {"required": ("closed_from",)} if closed else {}
    return [build("ObligationInput", id=o["id"], kind=o["kind"], name=o["name"], lender=o.get("lender"),
                  counterparty_inn=o.get("counterparty_inn"), principal=o.get("principal"),
                  annual_rate_bp=o.get("annual_rate_bp"), payment=o.get("payment"), payment_day=o.get("payment_day"),
                  first_payment_date=_opt_date(o.get("first_payment_date")), payments_total=o.get("payments_total"),
                  cost=o.get("cost"), life_years=o.get("life_years"), in_service_date=_opt_date(o.get("in_service_date")),
                  closed_from=closed_from_value(closed[o["id"]]) if o["id"] in closed else None, **extra)
            for o in DATA["obligations"]]


def planned_payments():
    return [build("PlannedPaymentInput", id=p["id"], date=D(p["date"]), name=p["name"], amount=p["amount"],
                  max_deferral_days=p["max_deferral_days"]) for p in DATA["planned_payments"]]


def counterparties():
    return [build("CounterpartyTermsInput", inn=c["inn"], name=c["name"], max_deferral_days=c["max_deferral_days"])
            for c in DATA["counterparties"]]


def div_round(n: int, d: int) -> int:
    """n / d rounded half away from zero, integers only (README rule 24); written here, not taken from the engine."""
    sign = -1 if n < 0 else 1
    return sign * ((abs(n) * 2 + d) // (d * 2))


def truncated_accounts(since: date) -> list:
    """The same clinic as if its history began on `since`: accounts open that day with the balance they had on its morning."""
    out = []
    for a in DATA["accounts"]:
        before = sum(t["amount"] for t in DATA["transactions"]
                     if t["account_id"] == a["id"] and t["status"] != "duplicate" and D(a["opening_date"]) <= D(t["date"]) < since)
        out.append(build("AccountInput", id=a["id"], name=a["name"], kind=a["type"], opening_balance=a["opening_balance"] + before,
                         opening_date=since))
    return out


def calendar_inputs(extra_tx=(), since=None, closed=None) -> dict:
    return {"accounts": truncated_accounts(since) if since else accounts(),
            "transactions": transactions(extra=extra_tx, since=since), "categories": categories(),
            "obligations": obligations(closed), "planned_payments": planned_payments(), "counterparties": counterparties()}


def month_arg(month: str) -> date:
    y, m = map(int, month.split("-"))
    return date(y, m, 1)


def run_calendar(fn, case="main", inputs=None, **extra):
    c = CASES[case]
    return plain(call(fn, **(inputs or calendar_inputs()), safe_balance=c["safe_balance"], as_of=D(c["as_of"]), days=22, **extra))


def reversed_inputs(inputs: dict) -> dict:
    return {k: (x[::-1] if isinstance(x, list) else x) for k, x in inputs.items()}


# ---------------------------------------------------------------- normalisation of engine output
def red(day) -> bool:
    """Red day in either shape of the engine output: `status` (contract) or `below_safe` (tester's first proposal)."""
    return day["status"] != "ok" if "status" in day else bool(day["below_safe"])


def payment_tuples(day) -> list:
    return sorted((p["name"], v(p["amount"]), p["source"]) for p in day["payments"])


def expected_payment_tuples(day) -> list:
    return sorted((p["name"], p["amount"], p["source"]) for p in day["payments"])


def recurring_tuples(series_list) -> set:
    """(name, category, day, amount) per slot; accepts nested `slots` or flat items with `day` and `amount`."""
    out = set()
    for s in series_list:
        slots = s.get("slots") or [s]
        for slot in slots:
            out.add((s.get("name") or s.get("counterparty_name"), s.get("category"), slot.get("day") or slot.get("nominal_day"),
                     v(slot.get("amount"))))
    return out


def profile_amounts(profile) -> list:
    """7 amounts Monday..Sunday from a list, a dict {0..6 | 'пн'..} or a list of {weekday, average|amount}."""
    if isinstance(profile, dict):
        if "by_weekday" in profile:
            return profile_amounts(profile["by_weekday"])
        keys = sorted(profile, key=lambda k: int(k) if str(k).isdigit() else ["пн", "вт", "ср", "чт", "пт", "сб", "вс"].index(k))
        return [v(profile[k]) for k in keys]
    if profile and isinstance(profile[0], dict):
        rows = sorted(profile, key=lambda r: r["weekday"])
        return [v(r.get("average", r.get("amount"))) for r in rows]
    return [v(x) for x in profile]


def recompute_with_move(days, move) -> list:
    """Closings after moving one payment (name, amount, from, to), recomputed from the engine's own days."""
    out, bal = [], v(days[0]["opening"])
    for d in days:
        pays = sum(v(p["amount"]) for p in d["payments"])
        if d["date"] == move["from"]:
            pays -= move["amount"]
        if d["date"] == move["to"]:
            pays += move["amount"]
        bal = bal + v(d["income_forecast"]) - pays
        out.append({"date": d["date"], "closing": bal})
    return out


# ---------------------------------------------------------------- text checks
SPACES = re.compile("[   \\s]")


def contains_amount(haystack: str, kopecks: int) -> bool:
    """The amount occurs as a number (not inside a longer number); ',00' after whole roubles is allowed."""
    squeezed = SPACES.sub("", haystack)
    rub, kop = divmod(abs(kopecks), 100)
    body = f"{rub}" + (f",{kop:02d}" if kop else "(?:,00)?")
    return re.search(r"(?<![\d,])" + body + r"(?!\d|,\d)", squeezed) is not None


def suggested_move(s, days) -> dict:
    """{name, from, to, amount} of a suggestion: the flat contract shape (`payment_id, payment_name, amount, from_date, to_date`,
    published 2026-10-17) or the nested `move{name, source, amount, from, to}` of the first proposal; if the amount is missing it
    is read from the payment on the from-day."""
    m = s.get("move") or s
    name = m.get("name") or s.get("payment_name")
    frm, to = m.get("from") or s.get("from_date"), m.get("to") or s.get("to_date")
    amount = m.get("amount")
    if amount is None:
        day = next(d for d in days if d["date"] == frm)
        pay = next(p for p in day["payments"] if p.get("id") == s.get("payment_id") or p["name"] == name)
        amount = pay["amount"]
    return {"name": name, "from": frm, "to": to, "amount": v(amount)}
