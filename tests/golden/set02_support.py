"""Shared helpers for the set02 golden tests (loading data, optional engine modules, in-memory import pipeline).

The pipeline below only COMPOSES proposed engine functions (see docs/handoff.md, 2026-10-11 tester -> backend-developer);
it contains no business logic of its own, so expected numbers still come from expected.json.
"""
import dataclasses
import importlib
import json
from datetime import date
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parent / "set02"
EXPECTED = json.loads((BASE / "expected.json").read_text(encoding="utf-8"))
INITIAL = json.loads((BASE / "initial.json").read_text(encoding="utf-8"))
TRUTH = json.loads((BASE / "truth.json").read_text(encoding="utf-8"))
NUM2LABEL = {v: k for k, v in TRUTH["numbers"].items()}
ACCOUNTS = {a["number"]: a["key"] for a in INITIAL["accounts"] if a["number"]}
SETTINGS = EXPECTED["assumptions"]


def read(name: str) -> bytes:
    return (BASE / name).read_bytes()


def vetmanager_raw() -> dict:
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (BASE / "vetmanager").glob("*.json")}


def engine(module: str, *attrs: str):
    """Import engine.<module>; skip with a clear reason while it (or an attribute) does not exist yet."""
    try:
        mod = importlib.import_module(f"engine.{module}")
    except ImportError as exc:
        pytest.skip(f"engine.{module} is not implemented yet ({exc}); interface proposed in docs/handoff.md")
    missing = [a for a in attrs if not hasattr(mod, a)]
    if missing:
        pytest.skip(f"engine.{module} has no {', '.join(missing)} yet; interface proposed in docs/handoff.md")
    return mod


def plain(obj):
    """dataclass / pydantic / dict / list -> plain dicts and lists (dates stay dates)."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: plain(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if hasattr(obj, "model_dump"):
        return plain(obj.model_dump())
    if isinstance(obj, dict):
        return {k: plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [plain(x) for x in obj]
    return obj


def as_date(v):
    return v if isinstance(v, date) else date.fromisoformat(str(v))


def leg_label(op: dict) -> str:
    """Label of an operation: document number -> label; transfer legs get the account tail."""
    lab = NUM2LABEL[op["number"]]
    return f"{lab}/{op['account_number'][-3:]}" if op["kind"] == "transfer" else lab


# ------------------------------------------------------------------ in-memory pipeline
class Db:
    """Tiny stand-in for the transactions table. Rows are dicts."""

    def __init__(self):
        self.rows = []
        self.rules = []
        self.paired = set()

    def add_row(self, **row):
        row.setdefault("external_id", None)
        row.setdefault("status", "ok")
        row.setdefault("duplicate_of", None)
        row.setdefault("category", None)
        row.setdefault("counterparty_inn", "")
        row.setdefault("description", "")
        self.rows.append(row)
        return row

    def row(self, label):
        return next(r for r in self.rows if r["label"] == label)


def refs(mod_dedup, rows):
    return [mod_dedup.TxRef(id=r["label"], account=r["account"], date=as_date(r["date"]), amount=r["amount"],
                            source=r["source"], kind=r["kind"]) for r in rows]


def seed_db(rules_mod):
    db = Db()
    db.rules = [rules_mod.Rule(match=r["match"], value=r["value"], direction=r["direction"], category=r["category"])
                for r in INITIAL["starter_rules"]]
    for e in INITIAL["existing_transactions"]:
        db.add_row(label=e["label"], account=ACCOUNTS_BY_KEY[e["account"]], date=e["date"], amount=e["amount"],
                   source=e["source"], kind="in" if e["amount"] > 0 else "out", category=e["category"])
    return db


ACCOUNTS_BY_KEY = {v: k for k, v in ACCOUNTS.items()}
ACCOUNTS_BY_KEY["cash"] = "cash"


def import_statement(db, raw, bank, dedup, rules):
    """parse -> legs -> idempotency -> rules -> duplicate pairs. Returns counters like POST /v1/imports/bank-statement."""
    parsed = bank.parse_1c_statement(raw)
    ops = [plain(o) for o in bank.statement_to_operations(parsed, ACCOUNTS)]
    result = plain(dedup.dedupe_incoming(ops, {r["external_id"] for r in db.rows if r["external_id"]}))
    fresh = sorted(result["new"], key=lambda o: (as_date(o["date"]), o["number"]))
    created = []
    for op in fresh:
        category = None if op["kind"] == "transfer" else rules.classify(op, db.rules)
        row = db.add_row(label=leg_label(op), account=op["account_number"], date=as_date(op["date"]).isoformat(),
                         amount=op["amount"], source="bank", kind=op["kind"], external_id=op["external_id"],
                         category=category, status="check" if (category is None and op["kind"] != "transfer") else "ok",
                         transfer_group=op.get("transfer_group"), description=op["description"],
                         counterparty_inn=op["counterparty_inn"])
        created.append(row)
        if row["kind"] != "transfer":
            candidates = [r for r in db.rows if r is not row and r["label"] not in db.paired
                          and r["status"] != "duplicate" and r["kind"] != "transfer"]
            pairs = dedup.find_duplicate_pairs(refs(dedup, [row]), refs(dedup, candidates), window_days=3)
            for p in map(plain, pairs):
                db.paired.add(p["original_id"])
                row["status"], row["duplicate_of"] = "duplicate", p["original_id"]
    return dict(parsed_documents=len(parsed.documents) if hasattr(parsed, "documents") else len(plain(parsed)["documents"]),
                skipped_in_file=len(result["skipped_in_file"]) if isinstance(result["skipped_in_file"], list) else result["skipped_in_file"],
                skipped_existing=len(result["skipped_existing"]) if isinstance(result["skipped_existing"], list) else result["skipped_existing"],
                created=len(created), duplicates=sum(1 for r in created if r["status"] == "duplicate"),
                check=sum(1 for r in created if r["status"] == "check"),
                rule_applied=sum(1 for r in created if r["kind"] != "transfer" and r["category"]),
                transfers=sum(1 for r in created if r["kind"] == "transfer"),
                created_labels=[r["label"] for r in created])
