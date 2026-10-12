"""Business behaviour of the Transactions screen. Numbers come from the engine; this module decides
what is stored, in which order, and which errors the client gets."""

import base64
import calendar
import re
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any
from uuid import UUID

from app.errors import not_found, validation_fields
from app.repo import Repository
from app.rows import AccountRow, CategoryRow, NewTx, TxRow
from app.schemas import figure_out
from app.schemas_tx import (
    CreatedRuleOut,
    NamedRefOut,
    ResolveDuplicateBody,
    ResolveDuplicateOut,
    RulePreviewOut,
    SummaryOut,
    TabCountsOut,
    TransactionCreate,
    TransactionListOut,
    TransactionPatch,
    TransactionPatchedOut,
)
from app.services.present import engine_rules, op_view, present_transactions
from engine.dedup import TxRef, find_duplicate_pairs
from engine.pii import strip_personal_names
from engine.rules import Rule, can_make_rule, retro_matches, rule_from_edit
from engine.transactions import summarize

MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
DEDUP_WINDOW_DAYS = 3
MANUAL_DESCRIPTION = "Внесено вручную"
STATUS_OK, STATUS_CHECK, STATUS_DUPLICATE = "ok", "check", "duplicate"


# ------------------------------------------------------------------ cursor
def encode_cursor(row: TxRow) -> str:
    return base64.urlsafe_b64encode(f"{row.date.isoformat()}|{row.id}".encode()).decode()


def decode_cursor(cursor: str | None) -> tuple[date, str] | None:
    if not cursor:
        return None
    try:
        day, _, row_id = base64.urlsafe_b64decode(cursor.encode()).decode().partition("|")
        UUID(row_id)
        return date.fromisoformat(day), row_id
    except (ValueError, UnicodeError) as exc:
        raise validation_fields({"cursor": "invalid"}) from exc


def month_bounds(month: str) -> tuple[date, date]:
    """First and last day of `YYYY-MM`."""
    if not MONTH_PATTERN.match(month):
        raise validation_fields({"month": "invalid"})
    year, number = int(month[:4]), int(month[5:])
    return date(year, number, 1), date(year, number, calendar.monthrange(year, number)[1])


# ------------------------------------------------------------------ lookups
async def get_row(repo: Repository, tx_id: str) -> TxRow:
    rows = await repo.get_transactions([tx_id])
    if not rows:
        raise not_found("Операция не найдена.")
    return rows[0]


def _find_category(categories: Sequence[CategoryRow], category_id: str) -> CategoryRow:
    for category in categories:
        if category.id == category_id:
            return category
    raise not_found("Статья не найдена.")


def _find_account(accounts: Sequence[AccountRow], account_id: str) -> AccountRow:
    for account in accounts:
        if account.id == account_id:
            return account
    raise not_found("Счёт не найден.")


# ------------------------------------------------------------------ list, counts, summary
async def list_page(
    repo: Repository,
    *,
    tab: str,
    date_from: date | None,
    date_to: date | None,
    limit: int,
    cursor: str | None,
) -> TransactionListOut:
    after = decode_cursor(cursor)
    rows = await repo.page_transactions(
        tab=tab, date_from=date_from, date_to=date_to, limit=limit + 1, after=after
    )
    page = list(rows[:limit])
    next_cursor = encode_cursor(page[-1]) if len(rows) > limit and page else None
    return TransactionListOut(items=await present_transactions(repo, page), next_cursor=next_cursor)


async def counts(repo: Repository) -> TabCountsOut:
    return TabCountsOut(**await repo.tab_counts())


async def summary(repo: Repository, month: str) -> SummaryOut:
    first, last = month_bounds(month)
    rows = await repo.summary_rows(first, last)
    result = summarize(
        [
            {
                "date": r.date,
                "amount": r.amount,
                "kind": r.kind,
                "status": r.status,
                "category": r.category,
                "source": r.source,
            }
            for r in rows
        ],
        month,
    )
    return SummaryOut(
        income=figure_out(result.income),
        expense=figure_out(result.expense),
        balance=figure_out(result.balance),
    )


# ------------------------------------------------------------------ manual entry
def _date_problems(day: date, today: date, account: AccountRow) -> dict[str, str]:
    if day > today:
        return {"date": "in_future"}
    if day < account.opening_date:
        return {"date": "before_opening"}
    return {}


async def _flag_duplicate(
    repo: Repository, account_id: str, day: date, amount: int, source: str
) -> str | None:
    """Id of the stored record that the new one duplicates, or None."""
    window = timedelta(days=DEDUP_WINDOW_DAYS)
    candidates = await repo.duplicate_candidates(day - window, day + window)
    new = TxRef("new", account_id, day, amount, source, "in" if amount > 0 else "out")
    pairs = find_duplicate_pairs([new], candidates, DEDUP_WINDOW_DAYS)
    return pairs[0].original_id if pairs else None


async def create_manual(
    repo: Repository, body: TransactionCreate, today: date
) -> TransactionPatchedOut:
    accounts = await repo.list_account_rows()
    account = _find_account(accounts, str(body.account_id))
    category: CategoryRow | None = None
    if body.category_id is not None:
        category = _find_category(await repo.list_categories(), str(body.category_id))
    problems = _date_problems(body.date, today, account)
    if problems:
        raise validation_fields(problems)
    amount = body.amount if body.kind == "in" else -body.amount
    original = await _flag_duplicate(repo, account.id, body.date, amount, "manual")
    description = strip_personal_names(body.comment or "") or MANUAL_DESCRIPTION
    status = STATUS_DUPLICATE if original else (STATUS_OK if category else STATUS_CHECK)
    ids = await repo.insert_transactions(
        [
            NewTx(
                account_id=account.id,
                date=body.date,
                description=description,
                amount=amount,
                kind=body.kind,
                source="manual",
                status=status,
                external_id=None,
                category_id=category.id if category else None,
                category_source="manual" if category else None,
                rule_id=None,
                duplicate_of=original,
                duplicate_state="pending" if original else None,
            )
        ]
    )
    created = await present_transactions(repo, await repo.get_transactions(ids))
    return TransactionPatchedOut(**created[0].model_dump(), rule=None)


# ------------------------------------------------------------------ category and rules
async def _matches_for(rule: Rule, repo: Repository, exclude_id: str) -> list[TxRow]:
    candidates = [r for r in await repo.uncategorised_checks() if r.id != exclude_id]
    by_id = {r.id: r for r in candidates}
    matched = retro_matches(rule, [{**op_view(r), "id": r.id} for r in candidates])
    return [by_id[str(m["id"])] for m in matched]


def _rule_key_exists(rules: Sequence[Rule], new: Rule) -> bool:
    return any(
        (r.match, r.value, r.direction) == (new.match, new.value, new.direction) for r in rules
    )


async def update_category(
    repo: Repository, tx_id: str, body: TransactionPatch
) -> TransactionPatchedOut:
    row = await get_row(repo, tx_id)
    category = _find_category(await repo.list_categories(), str(body.category_id))
    if row.kind == "transfer":
        raise validation_fields({"category_id": "invalid"})
    await repo.update_transaction(
        row.id,
        {
            "category_id": category.id,
            "category_source": "manual",
            "rule_id": None,
            "status": STATUS_OK if row.status == STATUS_CHECK else row.status,
        },
    )
    created = await _create_rule(repo, row, category) if body.create_rule else None
    refreshed = await present_transactions(repo, [await get_row(repo, row.id)])
    return TransactionPatchedOut(**refreshed[0].model_dump(), rule=created)


async def _create_rule(
    repo: Repository, row: TxRow, category: CategoryRow
) -> CreatedRuleOut | None:
    if not can_make_rule(op_view(row)):
        return None
    rule = rule_from_edit(op_view(row), category.id)
    stored = await repo.list_rules()
    if _rule_key_exists(engine_rules(stored), rule):
        return None
    created = await repo.insert_rule(
        match=rule.match,
        value=rule.value,
        display_name=row.counterparty_name or None,
        direction=rule.direction,
        category_id=category.id,
    )
    matches = await _matches_for(
        Rule(rule.match, rule.value, rule.direction, category.id, created.id), repo, row.id
    )
    for match in matches:
        await repo.update_transaction(
            match.id,
            {
                "category_id": category.id,
                "category_source": "rule",
                "rule_id": created.id,
                "status": STATUS_OK,
            },
        )
    return CreatedRuleOut(
        id=created.id,
        match_text=created.display_name or created.value,
        category=NamedRefOut(id=category.id, name=category.name),
        applied_count=len(matches),
    )


async def rule_preview(repo: Repository, tx_id: str, category_id: str) -> RulePreviewOut:
    row = await get_row(repo, tx_id)
    category = _find_category(await repo.list_categories(), category_id)
    if not can_make_rule(op_view(row)):
        return RulePreviewOut(
            can_create=False, already_exists=False, match_text=None, matches_count=0
        )
    rule = rule_from_edit(op_view(row), category.id)
    exists = _rule_key_exists(engine_rules(await repo.list_rules()), rule)
    matches = [] if exists else await _matches_for(rule, repo, row.id)
    return RulePreviewOut(
        can_create=not exists,
        already_exists=exists,
        match_text=row.counterparty_name or f"ИНН {rule.value}",
        matches_count=len(matches),
    )


# ------------------------------------------------------------------ duplicates
async def _pair_group(repo: Repository, row: TxRow) -> list[TxRow]:
    """The kept record and everything flagged as its duplicate."""
    anchor = row
    if row.duplicate_of:
        anchor = await get_row(repo, row.duplicate_of)
    members = await repo.get_duplicate_partners(anchor.id)
    group = [anchor, *members]
    if row.id not in {g.id for g in group}:
        group.append(row)
    return group


def _restored_status(row: TxRow) -> str:
    if row.kind == "transfer" or row.category_id:
        return STATUS_OK
    return STATUS_CHECK


async def resolve_duplicate(
    repo: Repository, tx_id: str, body: ResolveDuplicateBody
) -> ResolveDuplicateOut:
    row = await get_row(repo, tx_id)
    if (body.keep_id is None) == (not body.keep_both):
        raise validation_fields({"keep_id": "required"})
    group = await _pair_group(repo, row)
    ids = {g.id for g in group}
    if body.keep_id is not None and str(body.keep_id) not in ids:
        if not await repo.get_transactions([str(body.keep_id)]):
            raise not_found("Операция не найдена.")
        raise validation_fields({"keep_id": "invalid"})
    keep = None if body.keep_both else str(body.keep_id)
    for member in group:
        if keep is None:
            # both stay in the books; the link is kept so that the decision can be reverted
            changes: dict[str, Any] = {
                "status": _restored_status(member),
                "duplicate_state": None,
                "duplicate_dismissed": True,
            }
        elif member.id == keep:
            changes = {
                "status": _restored_status(member),
                "duplicate_of": None,
                "duplicate_state": None,
                "duplicate_dismissed": False,
            }
        else:
            changes = {
                "status": STATUS_DUPLICATE,
                "duplicate_of": keep,
                "duplicate_state": "confirmed",
                "duplicate_dismissed": False,
            }
        await repo.update_transaction(member.id, changes)
    refreshed = await present_transactions(repo, await repo.get_transactions([g.id for g in group]))
    kept = [t for t in refreshed if t.status != STATUS_DUPLICATE]
    duplicates = [t for t in refreshed if t.status == STATUS_DUPLICATE]
    return ResolveDuplicateOut(kept=kept, duplicates=duplicates)
