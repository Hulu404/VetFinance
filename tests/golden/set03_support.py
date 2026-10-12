"""Shared helpers for the set03 golden tests (dashboard, stage 2).

Loads data.json / expected.json and builds engine inputs. Contains NO business logic: every expected number
comes from expected.json (computed by tools/compute_expected_set03.py).

Tester-only switch: VF_ENGINE_OVERRIDE=<dir> puts <dir> (a folder that contains an `engine` package) in front of
backend/ so the tests can be run against a throw-away reference implementation. Not used in normal runs.
"""
import copy
import dataclasses
import importlib
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parent / "set03"
DATA = json.loads((BASE / "data.json").read_text(encoding="utf-8"))
EXPECTED = json.loads((BASE / "expected.json").read_text(encoding="utf-8"))
CASES = EXPECTED["cases"]
MAIN_AS_OF = "2026-09-09"


def case(as_of: str) -> dict:
    return next(c for c in CASES if c["as_of"] == as_of)


def plain(obj):
    """dataclass / pydantic / dict / list / Decimal -> plain dicts, lists, ints, floats."""
    from decimal import Decimal
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


def engine_dashboard():
    """Returns the engine.dashboard module or skips while it (or compute_dashboard) is missing."""
    override = os.environ.get("VF_ENGINE_OVERRIDE")
    if override:
        for name in [m for m in sys.modules if m == "engine" or m.startswith("engine.")]:
            del sys.modules[name]
        sys.path.insert(0, override)
    try:
        mod = importlib.import_module("engine.dashboard")
    except ImportError as exc:
        pytest.skip(f"engine.dashboard is not implemented yet ({exc}); interface proposed in docs/handoff.md")
    if not hasattr(mod, "compute_dashboard"):
        pytest.skip("engine.dashboard.compute_dashboard is not defined yet; interface proposed in docs/handoff.md")
    return mod


def _find_class(mod, name):
    cls = getattr(mod, name, None)
    if cls is None:
        try:
            cls = getattr(importlib.import_module("engine.balance"), name, None)
        except ImportError:
            cls = None
    return cls


def _build(cls, **kwargs):
    """Instantiate a dataclass with the fields it has (extra proposed fields are ignored, missing ones are an error)."""
    names = {f.name for f in dataclasses.fields(cls)}
    return cls(**{k: v for k, v in kwargs.items() if k in names})


def build_inputs(mod):
    """Engine inputs from data.json. Names of the classes are the tester's proposal (docs/handoff.md)."""
    A, T = _find_class(mod, "AccountInput"), _find_class(mod, "TransactionInput")
    S, L, V, N = (_find_class(mod, n) for n in ("SaleInput", "SaleLineInput", "VisitInput", "NormsInput"))
    missing = [n for n, c in (("AccountInput", A), ("TransactionInput", T), ("SaleInput", S), ("SaleLineInput", L),
                              ("VisitInput", V), ("NormsInput", N)) if c is None]
    if missing:
        pytest.skip(f"engine.dashboard has no {', '.join(missing)} yet; interface proposed in docs/handoff.md")
    doctors = {d["id"]: d["name"] for d in DATA["doctors"]}
    d = date.fromisoformat
    accounts = [_build(A, id=a["id"], name=a["name"], kind=a["type"], opening_balance=a["opening_balance"],
                       opening_date=d(a["opening_date"])) for a in DATA["accounts"]]
    txs = [_build(T, account_id=t["account_id"], date=d(t["date"]), amount=t["amount"], status=t["status"],
                  source=t["source"], kind=t["kind"], category=t["category"]) for t in DATA["transactions"]]
    sales = [_build(S, date=d(s["date"]), status=s["status"],
                    lines=tuple(_build(L, kind=ln["kind"], amount=ln["amount"]) for ln in s["lines"]))
             for s in DATA["sales"]]
    visits = [_build(V, date=d(v["date"]), doctor=doctors[v["doctor_id"]]) for v in DATA["visits"]]
    n = DATA["norms"]
    norms = _build(N, drugs_category=n["drugs"]["category"], drugs_max_pct=n["drugs"]["max_pct"],
                   margin_min_pct=n["profit_margin"]["min_pct"])
    return accounts, txs, sales, visits, norms


def run(mod, as_of: str, inputs=None):
    accounts, txs, sales, visits, norms = inputs or build_inputs(mod)
    return plain(mod.compute_dashboard(accounts, txs, sales, visits, norms, date.fromisoformat(as_of)))


def run_shuffled(mod, as_of: str):
    """Same data, reversed order of every list: the result must not depend on input order."""
    accounts, txs, sales, visits, norms = build_inputs(mod)
    return run(mod, as_of, (accounts[::-1], txs[::-1], sales[::-1], visits[::-1], norms))


def snapshot(inputs):
    return copy.deepcopy([list(x) if isinstance(x, (list, tuple)) else x for x in inputs])


# ---------------------------------------------------------------- text checks for the "Почему?" block
SPACES = re.compile("[   ]")


def norm_text(text: str) -> str:
    return SPACES.sub(" ", text).replace("−", "-")


def rub_text(kopecks: int) -> str:
    """'134 600,40' for 13460040; whole roubles without ',00' (an engine may print ',00': the regex allows it)."""
    rub, kop = divmod(abs(kopecks), 100)
    s = f"{rub:,}".replace(",", " ")
    return s + (f",{kop:02d}" if kop else "")


def contains_amount(haystack: str, kopecks: int) -> bool:
    pat = r"(?<![\d,])(?<!\d )" + re.escape(rub_text(kopecks)) + r"(?!\d)"
    return re.search(pat, haystack) is not None


def contains_number(haystack: str, token: str) -> bool:
    return re.search(r"(?<![\d,.])(?<!\d )" + re.escape(token) + r"(?![\d])", haystack) is not None


def why_text(advice: dict) -> str:
    why = advice["why"]
    return norm_text("\n".join([why["summary"], *why["steps"]]))
