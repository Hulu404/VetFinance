"""Categories and category rules (read side and rule deletion)."""

from datetime import date

from app.errors import not_found
from app.repo import Repository
from app.schemas import figure_out
from app.schemas_tx import (
    CategoriesOut,
    CategoryOut,
    CategoryRuleOut,
    CategoryRulesOut,
    NamedRefOut,
)
from app.services.present import rule_label
from engine.figure import Figure, FigureItem


def _applied_figure(this_month: int, total: int) -> Figure:
    return Figure(
        value=total,
        unit="count",
        breakdown=(
            FigureItem("В этом месяце", this_month, "count"),
            FigureItem("Раньше", total - this_month, "count"),
        ),
        source=("calc",),
        note="Сколько операций получили статью по этому правилу. Операция, по которой правило создано, не входит.",
    )


async def list_categories(repo: Repository) -> CategoriesOut:
    return CategoriesOut(
        items=[
            CategoryOut(
                id=c.id,
                name=c.name,
                type=c.type,
                norm_min_pct=c.norm_min_pct,
                norm_max_pct=c.norm_max_pct,
                norm_key=c.norm_key,
                direction=c.direction,
                payroll=c.payroll,
                in_service_recipes=c.in_service_recipes,
                doctor_percent=c.doctor_percent,
            )
            for c in await repo.list_categories()
        ]
    )


async def list_rules(repo: Repository, today: date) -> CategoryRulesOut:
    counts = await repo.rule_applied_counts(today.replace(day=1))
    items = []
    for rule in await repo.list_rules():
        this_month, total = counts.get(rule.id, (0, 0))
        items.append(
            CategoryRuleOut(
                id=rule.id,
                match="inn" if rule.match == "inn" else "text",
                match_text=rule_label(rule),
                direction="in"
                if rule.direction == "in"
                else ("out" if rule.direction == "out" else None),
                category=NamedRefOut(id=rule.category_id, name=rule.category_name),
                applied_count=figure_out(_applied_figure(this_month, total)),
                created_at=rule.created_at,
            )
        )
    return CategoryRulesOut(items=items)


async def delete_rule(repo: Repository, rule_id: str) -> None:
    if not await repo.delete_rule(rule_id):
        raise not_found("Правило не найдено.")
