"""Transactions, category rules, categories and the bank statement import."""

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, File, Form, Query, Response, UploadFile

from app.deps import NowDep, RepoDep, today_of
from app.errors import error_responses
from app.schemas_tx import (
    CategoriesOut,
    CategoryRulesOut,
    ImportOut,
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
from app.services import catalog, importer
from app.services import transactions as service

router = APIRouter(prefix="/v1", responses=error_responses(401, 403, 422))
MONTH_QUERY = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


@router.get("/transactions", response_model=TransactionListOut)
async def list_transactions(
    repo: RepoDep,
    tab: Literal["all", "check", "duplicates"] = "all",
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: str | None = None,
) -> TransactionListOut:
    return await service.list_page(
        repo, tab=tab, date_from=date_from, date_to=date_to, limit=limit, cursor=cursor
    )


@router.get("/transactions/counts", response_model=TabCountsOut)
async def transaction_counts(repo: RepoDep) -> TabCountsOut:
    return await service.counts(repo)


@router.get("/transactions/summary", response_model=SummaryOut)
async def transaction_summary(repo: RepoDep, month: Annotated[str, MONTH_QUERY]) -> SummaryOut:
    return await service.summary(repo, month)


@router.post(
    "/transactions",
    response_model=TransactionPatchedOut,
    status_code=201,
    responses=error_responses(404),
)
async def create_transaction(
    body: TransactionCreate, repo: RepoDep, now: NowDep
) -> TransactionPatchedOut:
    return await service.create_manual(repo, body, await today_of(repo, now))


@router.patch(
    "/transactions/{tx_id}", response_model=TransactionPatchedOut, responses=error_responses(404)
)
async def patch_transaction(
    tx_id: UUID, body: TransactionPatch, repo: RepoDep
) -> TransactionPatchedOut:
    return await service.update_category(repo, str(tx_id), body)


@router.get(
    "/transactions/{tx_id}/rule-preview",
    response_model=RulePreviewOut,
    responses=error_responses(404),
)
async def rule_preview(tx_id: UUID, category_id: UUID, repo: RepoDep) -> RulePreviewOut:
    return await service.rule_preview(repo, str(tx_id), str(category_id))


@router.post(
    "/transactions/{tx_id}/resolve-duplicate",
    response_model=ResolveDuplicateOut,
    responses=error_responses(404),
)
async def resolve_duplicate(
    tx_id: UUID, body: ResolveDuplicateBody, repo: RepoDep
) -> ResolveDuplicateOut:
    return await service.resolve_duplicate(repo, str(tx_id), body)


@router.get("/category-rules", response_model=CategoryRulesOut)
async def list_category_rules(repo: RepoDep, now: NowDep) -> CategoryRulesOut:
    return await catalog.list_rules(repo, await today_of(repo, now))


@router.delete("/category-rules/{rule_id}", status_code=204, responses=error_responses(404))
async def delete_category_rule(rule_id: UUID, repo: RepoDep) -> Response:
    await catalog.delete_rule(repo, str(rule_id))
    return Response(status_code=204)


@router.get("/categories", response_model=CategoriesOut)
async def list_categories(repo: RepoDep) -> CategoriesOut:
    return await catalog.list_categories(repo)


@router.post(
    "/imports/bank-statement", response_model=ImportOut, responses=error_responses(404, 429)
)
async def import_bank_statement(
    repo: RepoDep,
    file: Annotated[UploadFile, File()],
    account_id: Annotated[UUID | None, Form()] = None,
) -> ImportOut:
    raw = await file.read(importer.MAX_FILE_BYTES + 1)
    return await importer.import_bank_statement(repo, raw, str(account_id) if account_id else None)
