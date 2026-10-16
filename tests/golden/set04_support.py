"""Shared helpers for the set04 golden tests (reports, stage 3: P&L, norm, stock).

Loads data.json / expected.json and builds engine inputs. Contains NO business logic: every expected number comes from
expected.json (computed by tools/compute_expected_set04.py).

Interface under test is the tester's proposal (docs/handoff.md, "tester -> backend-developer (этап 3)"):
    engine.pnl.compute_pnl(categories, transactions, sales, card_payments, charges, month, acquiring_rate_bp,
                           bank_covered_to=None, as_of=None)
    engine.pnl.compute_direction_view(<same arguments>)
    engine.norm.compute_norm(categories, transactions, sales, card_payments, charges, writeoffs, benchmarks, month,
                             acquiring_rate_bp, bank_covered_to=None, as_of=None)
    engine.stock.compute_stock(items, batches, writeoffs, consumption, as_of)
Functions are called with the keyword arguments they accept (inspect.signature), input classes are built with the fields
they have, so a different but equivalent signature needs only a small change here. Tests skip while a module, a function
or an input class is missing.

Tester-only switch: VF_ENGINE_OVERRIDE=<dir> puts <dir> (a folder that contains an `engine` package) in front of backend/.
"""
import copy
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

BASE = Path(__file__).resolve().parent / "set04"
DATA = json.loads((BASE / "data.json").read_text(encoding="utf-8"))
EXPECTED = json.loads((BASE / "expected.json").read_text(encoding="utf-8"))
MONTHS = DATA["months"]          # 2026-07, 2026-08, 2026-09
EMPTY_MONTH = "2026-06"          # before the first data
MAIN_MONTH = "2026-09"
STOCK_AS_OF = DATA["stock"]["as_of"]
D = date.fromisoformat
CLASS_MODULES = ("engine.reports_inputs", "engine.pnl", "engine.norm", "engine.stock", "engine.balance",
                 "engine.dashboard_inputs", "engine.acquiring")


def plain(obj):
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: plain(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if hasattr(obj, "model_dump"):
        return plain(obj.model_dump())
    if isinstance(obj, dict):
        return {k: plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [plain(x) for x in obj]
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, date):
        return obj.isoformat()
    return obj


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
    accepted = {k: v for k, v in kwargs.items() if k in params}
    missing = [n for n, p in params.items() if p.default is inspect.Parameter.empty and n not in accepted
               and p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)]
    assert not missing, f"{fn.__name__} requires arguments the tests do not know: {missing}"
    return fn(**accepted)


def _find_class(class_name):
    for module in CLASS_MODULES:
        try:
            cls = getattr(importlib.import_module(module), class_name, None)
        except ImportError:
            continue
        if cls is not None:
            return cls
    return None


def _build(class_name, **kwargs):
    cls = _find_class(class_name)
    if cls is None:
        pytest.skip(f"input class {class_name} is not defined yet; interface proposed in docs/handoff.md")
    names = {f.name for f in dataclasses.fields(cls)}
    return cls(**{k: v for k, v in kwargs.items() if k in names})


def _dec(x):
    return None if x is None else Decimal(str(x))


def build_inputs() -> dict:
    """All inputs of the report engines from data.json, as keyword arguments (each function takes what it needs)."""
    categories = [_build("CategoryInput", name=c["name"], type=c["type"], norm_key=c["norm_key"], direction=c["direction"],
                         norm_min_pct=_dec(c["norm_min_pct"]), norm_max_pct=_dec(c["norm_max_pct"]), payroll=c["payroll"])
                  for c in DATA["categories"]]
    txs = [_build("TransactionInput", account_id=t["account_id"], date=D(t["date"]), amount=t["amount"], status=t["status"],
                  source=t["source"], kind=t["kind"], category=t["category"]) for t in DATA["transactions"]]
    sales = [_build("SaleInput", date=D(s["date"]), status=s["status"],
                    lines=tuple(_build("SaleLineInput", kind=ln["kind"], amount=ln["amount"]) for ln in s["lines"]))
             for s in DATA["sales"]]
    cards = [_build("CardPayment", date=D(p["date"]), amount=p["amount"]) for p in DATA["payments"] if p["method"] == "card"]
    charges = [_build("ObligationChargeInput", month=c["month"], obligation_id=c["obligation_id"], name=c["name"],
                      kind=c["kind"], amount=c["amount"]) for c in DATA["obligation_charges"]]
    benchmarks = [_build("BenchmarkInput", key=b["key"], label=b["label"], kind=b["kind"], min_pct=_dec(b["min_pct"]),
                         max_pct=_dec(b["max_pct"]), source="industry", sort=b["sort"]) for b in DATA["benchmarks"]]
    st = DATA["stock"]
    writeoffs = [_build("WriteoffInput", date=D(w["date"]), item=w["item"], qty=w["qty"], amount=w["amount"], reason=w["reason"])
                 for w in st["writeoffs"]]
    items = [_build("StockItemInput", id=i["id"], name=i["name"], last_movement=D(i["last_movement"])) for i in st["items"]]
    batches = [_build("StockBatchInput", item_id=b["item_id"], qty=b["qty"], unit_cost=b["unit_cost"],
                      expires_on=D(b["expires_on"]) if b["expires_on"] else None) for b in st["batches"]]
    consumption = [_build("ConsumptionInput", date=D(c["date"]), amount=c["amount"]) for c in st["consumption"]]
    return {"categories": categories, "transactions": txs, "sales": sales, "card_payments": cards, "charges": charges,
            "benchmarks": benchmarks, "writeoffs": writeoffs, "items": items, "batches": batches, "consumption": consumption,
            "acquiring_rate_bp": DATA["clinic"]["acquiring_rate_bp"],
            "bank_covered_to": D(DATA["bank_covered_to"]) if DATA.get("bank_covered_to") else None}


def reversed_inputs(inputs: dict) -> dict:
    return {k: (v[::-1] if isinstance(v, list) else v) for k, v in inputs.items()}


def snapshot(inputs: dict):
    return copy.deepcopy(inputs)


def month_arg(month: str) -> date:
    y, m = map(int, month.split("-"))
    return date(y, m, 1)


def run_pnl(fn, month, inputs=None, as_of=None):
    """as_of=None: the whole month (closed). as_of=date: the month is running, data up to and including that day."""
    if as_of is not None and "as_of" not in inspect.signature(fn).parameters:
        pytest.skip(f"{fn.__name__} has no as_of parameter yet (a running month); proposed in docs/handoff.md")
    return plain(call(fn, **(inputs or build_inputs()), month=month_arg(month), as_of=as_of))


run_norm = run_pnl


def run_stock(fn, as_of=STOCK_AS_OF, inputs=None, **extra):
    """extra: optional inputs only some implementations take (`revenue` / `month_revenue`: revenue of the write-off month, kopecks)."""
    return plain(call(fn, **(inputs or build_inputs()), as_of=D(as_of), **extra))


# ---------------------------------------------------------------- helpers over plain results
def labels(fig) -> dict:
    return {b["label"]: b["value"] for b in fig["breakdown"]}


def rows_by_key(result) -> dict:
    return {r["key"]: r for r in result["rows"]}


def items_by_key(result) -> dict:
    return {r["key"]: r for r in result["items"]}


# ---------------------------------------------------------------- text checks (export, tooltips)
SPACES = re.compile("[   \s]")   # no-break, narrow no-break, thin and ordinary spaces


def norm_text(text: str) -> str:
    return SPACES.sub(" ", text).replace("−", "-")


def rub_text(kopecks: int) -> str:
    """'134 600,40' for 13460040; whole roubles without ',00'."""
    rub, kop = divmod(abs(kopecks), 100)
    s = f"{rub:,}".replace(",", " ")
    return s + (f",{kop:02d}" if kop else "")


def contains_amount(haystack: str, kopecks: int) -> bool:
    """The amount occurs as a number (not inside a longer number); ',00' after whole roubles is allowed."""
    squeezed = SPACES.sub("", haystack)
    rub, kop = divmod(abs(kopecks), 100)
    body = f"{rub}" + (f",{kop:02d}" if kop else "(?:,00)?")
    return re.search(r"(?<![\d,])" + body + r"(?!\d|,\d)", squeezed) is not None
