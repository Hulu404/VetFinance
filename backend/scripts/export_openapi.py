"""Write backend/openapi.json from the application and put a real example into the dashboard schema.

Run from the repository root:  backend/.venv/Scripts/python backend/scripts/export_openapi.py
The example is the engine output for golden set 3 (tests/golden/set03/data.json, read only) at 2026-09-09,
passed through the API model, so it always matches the code and the numbers of the golden set.
"""

import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.main import create_app  # noqa: E402
from app.schemas_dash import dashboard_out  # noqa: E402
from engine.dashboard import (  # noqa: E402
    AccountInput,
    NormsInput,
    SaleInput,
    SaleLineInput,
    TransactionInput,
    VisitInput,
    compute_dashboard,
)

DATA = ROOT / "tests" / "golden" / "set03" / "data.json"
OUT = ROOT / "backend" / "openapi.json"
EXAMPLE_AS_OF = date(2026, 9, 9)


def example_dashboard() -> dict[str, object]:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    day = date.fromisoformat
    doctors = {d["id"]: d["name"] for d in data["doctors"]}
    accounts = [
        AccountInput(a["id"], a["name"], a["type"], a["opening_balance"], day(a["opening_date"]))
        for a in data["accounts"]
    ]
    transactions = [
        TransactionInput(
            t["account_id"],
            day(t["date"]),
            t["amount"],
            t["status"],
            t["source"],
            t["kind"],
            t["category"],
        )  # fmt: skip
        for t in data["transactions"]
    ]
    sales = [
        SaleInput(
            day(s["date"]),
            s["status"],
            tuple(SaleLineInput(line["kind"], line["amount"]) for line in s["lines"]),
        )
        for s in data["sales"]
    ]
    visits = [VisitInput(day(v["date"]), doctors[v["doctor_id"]]) for v in data["visits"]]
    norms = NormsInput(
        data["norms"]["drugs"]["category"],
        data["norms"]["drugs"]["max_pct"],
        data["norms"]["profit_margin"]["min_pct"],
    )
    result = compute_dashboard(accounts, transactions, sales, visits, norms, EXAMPLE_AS_OF)
    out = dashboard_out(
        result, data_as_of=datetime(2026, 9, 9, 1, 12, tzinfo=UTC), data_stale=False
    )
    example: dict[str, object] = out.model_dump(mode="json")
    return example


def main() -> None:
    schema = create_app().openapi()
    schema["info"]["description"] = "Generated from the code. Contract: docs/api-contract.md"
    schema["components"]["schemas"]["DashboardOut"]["example"] = example_dashboard()
    OUT.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(schema['paths'])} paths)")


if __name__ == "__main__":
    main()
