"""Build backend/app/examples/pricing_set06.json: the answers of the stage 5 stubs (golden set 6, tests/golden/set06).

Run from the repository root:  backend/.venv/Scripts/python backend/scripts/make_pricing_examples.py
Numbers are taken from expected.json and are not recomputed. Every object is passed through the API model, so the file
always matches app/schemas_pricing.py.
"""

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pricing_examples_eff as eff  # noqa: E402,I001
import pricing_examples_services as svc  # noqa: E402,I001
from pricing_examples_common import EXPECTED, ROOT, sid  # noqa: E402  (also puts backend/ on sys.path)

from app.schemas_pricing import (  # noqa: E402
    EfficiencyOut,
    EfficiencySettingsOut,
    RecipeOut,
    ServiceCostOut,
    ServiceItemOut,
    ServicesOut,
    StockItemsOut,
)

OUT = ROOT / "backend" / "app" / "examples" / "pricing_set06.json"
CASE_EXAMPLES = {
    "loss": "S6",
    "partial_item_no_cost": "S5",
    "no_recipe": "S10",
    "empty_recipe": "S11",
    "manual_no_sales": "M1",
}


def dump(model: Any) -> dict[str, Any]:
    out: dict[str, Any] = model.model_dump(mode="json", by_alias=True)
    return out


def _no_expenses(s: dict[str, Any]) -> dict[str, Any]:
    """The service as the engine returns it when the month has no expenses."""
    out = {**s, "parts": {**s["parts"], "acquiring": None, "taxes": None, "fixed": None}}
    if s["price_basis"] != "manual" and s["id"] not in ("S1", "S4", "S5", "S6", "S8", "S11", "M1"):
        out["parts"]["doctor_pay"] = None  # the clinic average percent needs the P&L
    out.update(net_profit=None, net_margin_pct=None, monthly_profit=None, shares=None)
    out["missing"] = [*s["missing"], "hour_cost", "no_expenses"]
    out["status"] = "no_recipe" if s["status"] == "no_recipe" else "partial"
    return out


def build() -> dict[str, Any]:
    main = EXPECTED["cases"]["main"]
    services = {s["id"]: s for s in main["services"]}
    ctx = {"hour_cost": main["hour_cost"]}
    items = [svc.list_item(s) for s in main["services"]]
    counts = main["counts"]
    listing = ServicesOut.model_validate(
        {
            "basis_month": "2026-09",
            "headline": svc.headline(items, counts),
            "counts": counts,
            "items": items,
            "next_cursor": None,
        }
    )
    cards = {
        sid(k): dump(ServiceCostOut.model_validate(svc.card(s, ctx))) for k, s in services.items()
    }
    recipes = {sid(k): dump(RecipeOut.model_validate(svc.recipe(s))) for k, s in services.items()}
    no_hours = EXPECTED["cases"]["no_hours"]
    s4_no_hours = next(s for s in no_hours["services"] if s["id"] == "S4")
    ctx_none = {"hour_cost": None}
    variants = {name: cards[sid(key)] for name, key in CASE_EXAMPLES.items()}
    variants["no_hour_cost"] = dump(
        ServiceCostOut.model_validate(svc.card(s4_no_hours, {"hour_cost": None}))
    )
    # a month without a statement (decision 14): no profit, no tax and commission taken from an empty P&L
    blank = [_no_expenses(x) for x in main["services"]]
    variants["no_expenses"] = dump(ServiceCostOut.model_validate(svc.card(blank[1], ctx_none)))
    blank_items = [svc.list_item(x) for x in blank]
    blank_list = ServicesOut.model_validate(
        {
            "basis_month": "2026-09",
            "headline": "Нет данных о расходах за сентябрь: прибыль услуг не считаем. Загрузите выписку банка.",
            "counts": {"all": len(blank), "loss": 0, "no_recipe": main["counts"]["no_recipe"]},
            "items": blank_items,
            "next_cursor": None,
        }
    )
    created = {
        **items[0],
        "id": sid("created"),
        "name": "Груминг: стрижка",
        "group": "Груминг",
        "source": "manual",
        "unit_label": "раз",
    }
    created.update(
        visits_month=svc.count_fig(0, "Оказана за сентябрь", ["vetmanager"], "Продаж нет."),
        margin_pct=None,
        monthly_profit=None,
        status="no_recipe",
    )
    created["price"] = svc.rub_fig(
        180000, "Цена, введённая вручную", ["manual"], "Продаж по услуге за 90 дней нет."
    )
    efficiency = {
        k: dump(EfficiencyOut.model_validate(eff.efficiency(k))) for k in EXPECTED["cases"]
    }
    return {
        "as_of": EXPECTED["as_of"],
        "month": EXPECTED["month"],
        "services": dump(listing),
        "services_no_expenses": dump(blank_list),
        "cards": cards,
        "card_variants": variants,
        "recipes": recipes,
        "stock_items": dump(StockItemsOut.model_validate(svc.stock_items())),
        "created_service": dump(ServiceItemOut.model_validate(created)),
        "efficiency": efficiency,
        "efficiency_settings": dump(EfficiencySettingsOut.model_validate(eff.settings())),
    }


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
