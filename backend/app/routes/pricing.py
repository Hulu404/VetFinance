"""Stage 5 routes: price list, cost card, techcard, stock items, efficiency (docs/api-contract.md).

The numbers come from the engines through app/services/pricing.py.
"""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Body, Response

from app.deps import NowDep, RepoDep, today_of
from app.errors import error_responses
from app.schemas_pricing import (
    EfficiencyOut,
    EfficiencySettingsBody,
    EfficiencySettingsOut,
    RecipeBody,
    RecipeOut,
    ServiceCostOut,
    ServiceCreateBody,
    ServiceItemOut,
    ServicePatchBody,
    ServicesOut,
    StockItemsOut,
)
from app.services import pricing as service

router = APIRouter(prefix="/v1", responses=error_responses(401, 403, 422))
BodyAny = Annotated[Any, Body()]


def _doc(model: Any) -> dict[str, Any]:
    return {
        "required": True,
        "content": {"application/json": {"schema": model.model_json_schema()}},
    }


async def _as_of(repo: RepoDep, now: NowDep, as_of: date | None) -> date:
    return as_of or await today_of(repo, now)


# ------------------------------------------------------------------ price list
@router.get("/services", response_model=ServicesOut)
async def list_services(
    repo: RepoDep,
    now: NowDep,
    sort: str = "margin",
    order: str = "asc",
    filter: str = "all",  # noqa: A002 (the name is the contract's)
    q: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
    as_of: date | None = None,
) -> ServicesOut:
    return await service.list_services(
        repo, await _as_of(repo, now, as_of), sort, order, filter, q, limit, cursor
    )


@router.post(
    "/services",
    status_code=201,
    response_model=ServiceItemOut,
    openapi_extra={"requestBody": _doc(ServiceCreateBody)},
)
async def create_service(repo: RepoDep, now: NowDep, body: BodyAny) -> ServiceItemOut:
    return await service.create_service(repo, await today_of(repo, now), body)


@router.patch(
    "/services/{service_id}",
    status_code=204,
    responses=error_responses(404),
    openapi_extra={"requestBody": _doc(ServicePatchBody)},
)
async def patch_service(service_id: str, repo: RepoDep, body: BodyAny) -> Response:
    """Only a manual service can be changed; a service from Vetmanager answers 403."""
    await service.patch_service(repo, service_id, body)
    return Response(status_code=204)


@router.delete("/services/{service_id}", status_code=204, responses=error_responses(404))
async def delete_service(service_id: str, repo: RepoDep) -> Response:
    await service.delete_service(repo, service_id)
    return Response(status_code=204)


@router.get(
    "/services/{service_id}/cost", response_model=ServiceCostOut, responses=error_responses(404)
)
async def service_cost(
    service_id: str, repo: RepoDep, now: NowDep, as_of: date | None = None
) -> ServiceCostOut:
    return await service.service_cost(repo, await _as_of(repo, now, as_of), service_id)


@router.get(
    "/services/{service_id}/recipe", response_model=RecipeOut, responses=error_responses(404)
)
async def get_recipe(
    service_id: str, repo: RepoDep, now: NowDep, as_of: date | None = None
) -> RecipeOut:
    return await service.get_recipe(repo, await _as_of(repo, now, as_of), service_id)


@router.put(
    "/services/{service_id}/recipe",
    response_model=RecipeOut,
    responses=error_responses(404),
    openapi_extra={"requestBody": _doc(RecipeBody)},
)
async def put_recipe(
    service_id: str, repo: RepoDep, now: NowDep, body: BodyAny, as_of: date | None = None
) -> RecipeOut:
    return await service.put_recipe(repo, await _as_of(repo, now, as_of), service_id, body)


@router.get("/stock/items", response_model=StockItemsOut)
async def stock_items(
    repo: RepoDep, now: NowDep, q: str | None = None, limit: int = 50, cursor: str | None = None,
    as_of: date | None = None,
) -> StockItemsOut:  # fmt: skip
    return await service.stock_items(repo, await _as_of(repo, now, as_of), q, limit, cursor)


# ------------------------------------------------------------------ efficiency
@router.get("/efficiency", response_model=EfficiencyOut)
async def efficiency(
    repo: RepoDep, now: NowDep, month: str | None = None, as_of: date | None = None
) -> EfficiencyOut:
    return await service.efficiency(repo, await _as_of(repo, now, as_of), month)


@router.get("/efficiency/settings", response_model=EfficiencySettingsOut)
async def get_efficiency_settings(repo: RepoDep) -> EfficiencySettingsOut:
    return await service.get_settings(repo)


@router.put(
    "/efficiency/settings",
    response_model=EfficiencySettingsOut,
    openapi_extra={"requestBody": _doc(EfficiencySettingsBody)},
)
async def put_efficiency_settings(repo: RepoDep, body: BodyAny) -> EfficiencySettingsOut:
    return await service.put_settings(repo, body)
