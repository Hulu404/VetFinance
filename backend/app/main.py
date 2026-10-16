from dataclasses import asdict
from datetime import date
from zoneinfo import ZoneInfo

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.deps import NowDep, RepoDep
from app.errors import error_responses, install_error_handlers
from app.routes import acquiring, connections, reports, transactions
from app.schemas import AccountOut, AccountsOut, ClinicOut, ClinicPatch
from app.schemas_dash import DashboardOut, dashboard_out
from app.services.connections import data_is_stale
from app.settings import Settings, get_settings
from engine.dashboard import compute_dashboard, history_start

router = APIRouter(prefix="/v1", responses=error_responses(401, 403, 422))

NOT_NULL_FIELDS = ("name", "timezone", "safe_balance")


@router.get("/clinic", response_model=ClinicOut)
async def get_clinic(repo: RepoDep) -> ClinicOut:
    return ClinicOut(**asdict(await repo.get_clinic()))


@router.patch("/clinic", response_model=ClinicOut)
async def patch_clinic(body: ClinicPatch, repo: RepoDep) -> ClinicOut:
    changes = body.model_dump(exclude_unset=True)
    for key in NOT_NULL_FIELDS:  # NOT NULL in the database: null means "leave as is"
        if key in changes and changes[key] is None:
            del changes[key]
    return ClinicOut(**asdict(await repo.update_clinic(changes)))


@router.get("/accounts", response_model=AccountsOut)
async def list_accounts(repo: RepoDep) -> AccountsOut:
    accounts = await repo.list_accounts()
    return AccountsOut(
        items=[
            AccountOut(
                id=a.id,
                name=a.name,
                kind=a.kind,
                opening_balance=a.opening_balance,
                opening_date=a.opening_date,
            )
            for a in accounts
        ]
    )


@router.get("/dashboard", response_model=DashboardOut)
async def dashboard(repo: RepoDep, now: NowDep, as_of: date | None = None) -> DashboardOut:
    clinic = await repo.get_clinic()
    today = now.astimezone(ZoneInfo(clinic.timezone)).date()
    as_of = as_of or today
    since = history_start(as_of)
    result = compute_dashboard(
        await repo.list_accounts(),
        await repo.list_transactions(as_of),
        await repo.list_sales(since, as_of),
        await repo.list_visits(since, as_of),
        await repo.get_norms(),
        as_of,
    )
    return dashboard_out(
        result,
        data_as_of=await repo.last_data_at(),
        data_stale=await data_is_stale(repo, now, today),
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="VetFinance API", version="0.1.0")
    origins = [o.strip() for o in (settings or get_settings()).cors_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    install_error_handlers(app)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(router)
    app.include_router(transactions.router)
    app.include_router(acquiring.router)
    app.include_router(connections.router)
    app.include_router(reports.router)
    return app


app = create_app()
