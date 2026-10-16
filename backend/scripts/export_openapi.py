"""Write backend/openapi.json from the application and put real examples into the dashboard and report schemas.

Run from the repository root:  backend/.venv/Scripts/python backend/scripts/export_openapi.py
The examples are the real output of the code: the dashboard for golden set 3 (tests/golden/set03, read
only) at 2026-09-09, the three reports of stage 3 for golden set 4 (tests/golden/set04, September 2026), each
passed through the API model, so they always match the code and the numbers of the golden sets.
"""

import asyncio
import json
import sys
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.main import create_app  # noqa: E402
from app.schemas_dash import dashboard_out  # noqa: E402
from app.services import reports as report_service  # noqa: E402
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


def example_reports() -> dict[str, dict[str, object]]:
    """Answers of the report endpoints for golden set 4 (September 2026), produced by the real services."""
    from tests.set04_loader import load_set04  # the in-memory repository of the tests

    repo = load_set04()
    moscow = timezone(timedelta(hours=3))
    data_as_of = datetime(2026, 10, 1, 4, 12, tzinfo=moscow)
    closed = report_service.Window(date(2026, 10, 1), date(2026, 9, 1))
    at_month_end = report_service.Window(date(2026, 9, 30), date(2026, 9, 1))

    async def build() -> dict[str, dict[str, object]]:
        pnl = await report_service.build_pnl(repo, closed, "direction")
        norm = await report_service.build_norm(repo, closed)
        stock = await report_service.build_stock(repo, at_month_end)
        idle = await report_service.build_idle(repo, at_month_end, "all", None, 10)
        models = {
            "PnlOut": pnl.model_copy(update={"data_as_of": data_as_of}),
            "NormOut": norm.model_copy(update={"data_as_of": data_as_of}),
            "StockOut": stock.model_copy(update={"data_as_of": data_as_of}),
            "StockIdleOut": idle,
        }
        return {k: v.model_dump(mode="json", by_alias=True) for k, v in models.items()}

    return asyncio.run(build())


def main() -> None:
    schema = create_app().openapi()
    schema["info"]["description"] = "Generated from the code. Contract: docs/api-contract.md"
    schemas = schema["components"]["schemas"]
    schemas["DashboardOut"]["example"] = example_dashboard()
    # Stage 3 reports: the answers of the real services for golden set 4, see example_reports()
    for name, example in example_reports().items():
        schemas[name]["example"] = example
    OUT.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(schema['paths'])} paths)")


if __name__ == "__main__":
    main()
