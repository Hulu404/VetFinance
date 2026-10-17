"""Stage 4 routes: payment calendar, obligations, counterparty deferral (docs/api-contract.md, "Планирование").

The routes check the request and call app/services/planning.py; the numbers come from the engines.
"""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Body, Response

from app.deps import NowDep, RepoDep, today_of
from app.errors import error_responses, validation_fields
from app.schemas_planning import (
    CalendarOut,
    CounterpartyOut,
    CounterpartyPatch,
    EquipmentBody,
    EquipmentOut,
    LeaseBody,
    LoanBody,
    LoanOut,
    ManualPaymentBody,
    ManualPaymentOut,
    ObligationsOut,
)
from app.services import planning as service

router = APIRouter(prefix="/v1", responses=error_responses(401, 403, 422))

WINDOW_DAYS = 22


def _body_doc(*models: Any) -> dict[str, Any]:
    return {
        "required": True,
        "content": {
            "application/json": {"schema": {"oneOf": [m.model_json_schema() for m in models]}}
        },
    }


# ------------------------------------------------------------------ calendar
@router.get("/calendar", response_model=CalendarOut)
async def calendar(
    repo: RepoDep,
    now: NowDep,
    days: str = str(WINDOW_DAYS),
    as_of: date | None = None,
    preview: str | None = None,
) -> CalendarOut:
    if days != str(WINDOW_DAYS):
        raise validation_fields({"days": "invalid"})
    return await service.build_calendar(repo, as_of or await today_of(repo, now), preview)


@router.post("/calendar/payments", status_code=201, response_model=ManualPaymentOut)
async def add_payment(body: ManualPaymentBody, repo: RepoDep, now: NowDep) -> ManualPaymentOut:
    return await service.add_manual_payment(repo, body, await today_of(repo, now))


@router.delete("/calendar/payments/{payment_id}", status_code=204, responses=error_responses(404))
async def delete_payment(payment_id: str, repo: RepoDep) -> Response:
    await service.delete_manual_payment(repo, payment_id)
    return Response(status_code=204)


# ------------------------------------------------------------------ counterparties
@router.patch(
    "/counterparties/{counterparty_id}",
    response_model=CounterpartyOut,
    responses=error_responses(404),
)
async def patch_counterparty(
    counterparty_id: str, body: CounterpartyPatch, repo: RepoDep
) -> CounterpartyOut:
    """Deferral the counterparty allows, in days (0: payments are not moved)."""
    return await service.set_deferral(repo, counterparty_id, body.max_deferral_days)


# ------------------------------------------------------------------ obligations
_BODY_DOC = _body_doc(LoanBody, LeaseBody, EquipmentBody)


@router.get("/obligations", response_model=ObligationsOut)
async def obligations(repo: RepoDep, now: NowDep, as_of: date | None = None) -> ObligationsOut:
    return await service.build_obligations(repo, as_of or await today_of(repo, now))


@router.post(
    "/obligations",
    status_code=201,
    response_model=LoanOut | EquipmentOut,
    openapi_extra={"requestBody": _BODY_DOC},
)
async def create_obligation(
    repo: RepoDep, now: NowDep, body: Annotated[Any, Body()]
) -> LoanOut | EquipmentOut:
    return await service.create_obligation(repo, body, await today_of(repo, now))


@router.patch(
    "/obligations/{obligation_id}",
    response_model=LoanOut | EquipmentOut,
    responses=error_responses(404),
    openapi_extra={"requestBody": _BODY_DOC},
)
async def patch_obligation(
    obligation_id: str, repo: RepoDep, now: NowDep, body: Annotated[Any, Body()]
) -> LoanOut | EquipmentOut:
    return await service.patch_obligation(repo, obligation_id, body, await today_of(repo, now))


@router.delete("/obligations/{obligation_id}", status_code=204, responses=error_responses(404))
async def close_obligation(obligation_id: str, repo: RepoDep, now: NowDep) -> Response:
    """Closes the obligation from the current month; accruals of earlier months stay."""
    await service.close_obligation(repo, obligation_id, await today_of(repo, now))
    return Response(status_code=204)
