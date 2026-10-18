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
from typing import Any

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


def example_planning() -> dict[str, dict[str, object]]:
    """Calendar, obligations, a manual payment, a counterparty and the `cash_gap` advice for golden set 5."""
    from app.planning_out import manual_payment_out
    from app.schemas_planning import CounterpartyOut
    from app.services import planning as planning_service
    from tests.set05_loader import load_set05

    repo = load_set05()
    as_of = date(2026, 10, 7)
    data_as_of = datetime(2026, 10, 7, 4, 12, tzinfo=timezone(timedelta(hours=3)))

    async def build() -> dict[str, dict[str, object]]:
        calendar = (await planning_service.build_calendar(repo, as_of)).model_copy(
            update={"data_as_of": data_as_of}
        )
        gap = await planning_service.cash_gap(repo, as_of)
        categories = {c.name: c.id for c in await repo.list_categories()}
        manual = manual_payment_out(repo.planned[0], categories)
        terms = repo.terms["5003012345"]
        counterparty = CounterpartyOut(
            id=terms.inn, name=terms.name, max_deferral_days=terms.max_deferral_days
        )
        assert gap is not None  # noqa: S101 (the example has a gap)
        models = {
            "calendar": calendar,
            "obligations": await planning_service.build_obligations(repo, as_of),
            "manual_payment": manual,
            "counterparty": counterparty,
            "cash_gap": gap,
        }
        return {
            k: v.model_dump(mode="json", by_alias=True, exclude_none=False)
            for k, v in models.items()
        }

    return asyncio.run(build())


def example_pricing() -> dict[str, Any]:
    """Stage 5 stub answers (golden set 6), built by scripts/make_pricing_examples.py into app/examples."""
    path = ROOT / "backend" / "app" / "examples" / "pricing_set06.json"
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def main() -> None:
    schema = create_app().openapi()
    schema["info"]["description"] = "Generated from the code. Contract: docs/api-contract.md"
    schemas = schema["components"]["schemas"]
    schemas["DashboardOut"]["example"] = example_dashboard()
    # Stage 3 reports: the answers of the real services for golden set 4, see example_reports()
    for name, example in example_reports().items():
        schemas[name]["example"] = example
    # Stage 4: the answers of the real services for golden set 5 (tests/golden/set05), as_of 2026-10-07
    planning = example_planning()
    schemas["CalendarOut"]["example"] = planning["calendar"]
    schemas["ObligationsOut"]["example"] = planning["obligations"]
    schemas["ManualPaymentOut"]["example"] = planning["manual_payment"]
    schemas["CounterpartyOut"]["example"] = planning["counterparty"]
    schemas["AdviceOut"]["example"] = planning["cash_gap"]
    # Stage 5: the stubs answer with golden set 6 (tests/golden/set06), as_of 2026-10-01; named states go to x-examples
    pricing = example_pricing()
    first_card = next(iter(pricing["cards"].values()))
    schemas["ServicesOut"]["example"] = pricing["services"]
    schemas["ServicesOut"]["x-examples"] = {"no_expenses": pricing["services_no_expenses"]}
    schemas["ServiceCostOut"]["example"] = first_card
    schemas["ServiceCostOut"]["x-examples"] = pricing["card_variants"]
    schemas["ServiceItemOut"]["example"] = pricing["created_service"]
    schemas["RecipeOut"]["example"] = next(iter(pricing["recipes"].values()))
    schemas["StockItemsOut"]["example"] = pricing["stock_items"]
    schemas["EfficiencyOut"]["example"] = pricing["efficiency"]["main"]
    schemas["EfficiencyOut"]["x-examples"] = pricing["efficiency"]
    schemas["EfficiencySettingsOut"]["example"] = pricing["efficiency_settings"]
    OUT.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(schema['paths'])} paths)")


if __name__ == "__main__":
    main()
