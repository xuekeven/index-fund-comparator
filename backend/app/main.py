from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings, get_settings
from app.models import (
    ComparisonResponse,
    FundListResponse,
    FundTagResponse,
    FundTagUpdate,
    HealthResponse,
    IndexSummary,
    InvestmentNoteCreate,
    InvestmentNoteItem,
    InvestmentNoteUpdate,
    NavSeriesResponse,
)
from app.repository import FundRepository, get_repository
from app.sync_jobs import SyncJobBusyError, SyncTaskKey, sync_job_runner


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="为响应式 Web 提供按份额类别组织的指数基金 EOD 比较数据。",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.parsed_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

RepositoryDep = Annotated[FundRepository, Depends(get_repository)]
FRONTEND_DIST_DIR = Path(__file__).resolve().parents[2] / "frontend" / "dist"
DISABLED_DOCUMENTATION_PATHS = {"docs", "redoc", "openapi.json"}


@app.get(f"{settings.api_prefix}/health", response_model=HealthResponse)
def health(current_settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=current_settings.app_version,
        data_mode=current_settings.data_mode,
        checked_at=datetime.now(UTC),
    )


@app.get(f"{settings.api_prefix}/health/ready", response_model=HealthResponse)
def readiness(
    repository: RepositoryDep,
    current_settings: Annotated[Settings, Depends(get_settings)],
) -> HealthResponse:
    try:
        ready = repository.is_ready()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Data service is unavailable") from exc
    if not ready:
        raise HTTPException(status_code=503, detail="Data service is unavailable")
    return HealthResponse(
        status="ok",
        version=current_settings.app_version,
        data_mode=current_settings.data_mode,
        checked_at=datetime.now(UTC),
    )


@app.get(f"{settings.api_prefix}/indices", response_model=list[IndexSummary])
def list_indices(repository: RepositoryDep) -> list[IndexSummary]:
    return repository.list_indices()


@app.get(f"{settings.api_prefix}/indices/{{index_id}}/funds", response_model=FundListResponse)
def list_index_funds(
    index_id: str,
    repository: RepositoryDep,
    venue: Literal["场内", "场外"] | None = None,
    exchange: Annotated[
        list[Literal["上交所", "深交所"]] | None,
        Query(),
    ] = None,
    structure: str | None = None,
) -> FundListResponse:
    index = repository.get_index(index_id)
    if index is None:
        raise HTTPException(status_code=404, detail="Index not found")

    funds = repository.list_funds(index_id)
    if venue:
        funds = [fund for fund in funds if fund.trading_venue.value == venue]
    if exchange:
        funds = [fund for fund in funds if fund.exchange in exchange]
    if structure:
        funds = [fund for fund in funds if fund.product_structure.value == structure]

    freshness = repository.get_data_freshness(
        index_id,
        venue=venue,
        exchanges=tuple(exchange or ()),
    )
    return FundListResponse(
        index=index,
        items=funds,
        total=len(funds),
        last_synced_at=freshness.latest_at,
        data_freshness=freshness,
        generated_at=datetime.now(UTC),
        data_mode=settings.data_mode,
    )


@app.get(f"{settings.api_prefix}/comparisons", response_model=ComparisonResponse)
def compare_funds(
    repository: RepositoryDep,
    fund_codes: Annotated[
        list[str], Query(alias="fundCodes", min_length=2, max_length=4)
    ],
) -> ComparisonResponse:
    unique_codes = list(dict.fromkeys(fund_codes))
    if len(unique_codes) < 2:
        raise HTTPException(status_code=422, detail="At least two distinct fund codes are required")

    items = repository.get_funds(unique_codes)
    if len(items) < 2:
        raise HTTPException(status_code=404, detail="Fewer than two matching funds")

    missing = sorted(set(unique_codes) - {item.code for item in items})
    index_ids = {item.index_id for item in items}
    exact_benchmarks = {item.exact_benchmark for item in items}
    warnings: list[str] = []
    if missing:
        warnings.append(f"未找到基金代码：{', '.join(missing)}")
    if len(index_ids) > 1:
        warnings.append("所选基金不属于同一指数，不建议直接比较跟踪表现。")
    elif len(exact_benchmarks) > 1:
        warnings.append("所选基金的精确跟踪基准不同，请结合各基金合同口径比较。")

    return ComparisonResponse(
        items=items,
        generated_at=datetime.now(UTC),
        warnings=warnings,
        metadata={"dataMode": settings.data_mode, "rowGranularity": "fund_share_class"},
    )


@app.get(f"{settings.api_prefix}/funds/{{fund_code}}/nav", response_model=NavSeriesResponse)
def get_fund_nav(
    fund_code: str,
    repository: RepositoryDep,
    start_date: Annotated[date | None, Query(alias="startDate")] = None,
    end_date: Annotated[date | None, Query(alias="endDate")] = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
) -> NavSeriesResponse:
    if start_date is not None and end_date is not None and start_date > end_date:
        raise HTTPException(status_code=422, detail="startDate must not be after endDate")
    fund = repository.get_fund(fund_code)
    if fund is None:
        raise HTTPException(status_code=404, detail="Fund not found")
    return NavSeriesResponse(
        fund_code=fund_code,
        items=repository.get_nav(fund_code, start_date, end_date, limit),
        source_name=fund.source_name,
        generated_at=datetime.now(UTC),
    )


@app.put(
    f"{settings.api_prefix}/funds/{{fund_code}}/tags",
    response_model=FundTagResponse,
)
def update_fund_tags(
    fund_code: str,
    payload: FundTagUpdate,
    repository: RepositoryDep,
) -> FundTagResponse:
    tags = repository.set_fund_tags(fund_code, payload.tags)
    if tags is None:
        raise HTTPException(status_code=404, detail="Fund not found")
    return FundTagResponse(fund_code=fund_code, tags=tags)


@app.get(
    f"{settings.api_prefix}/notes",
    response_model=list[InvestmentNoteItem],
)
def list_investment_notes(
    repository: RepositoryDep,
    q: str | None = None,
    category: Literal["长期", "实时"] | None = None,
    year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
) -> list[InvestmentNoteItem]:
    return repository.list_notes(query=q, category=category, year=year)


@app.post(
    f"{settings.api_prefix}/notes",
    response_model=InvestmentNoteItem,
    status_code=201,
)
def create_investment_note(
    payload: InvestmentNoteCreate,
    repository: RepositoryDep,
) -> InvestmentNoteItem:
    return repository.create_note(payload)


@app.put(
    f"{settings.api_prefix}/notes/{{note_id}}",
    response_model=InvestmentNoteItem,
)
def update_investment_note(
    note_id: int,
    payload: InvestmentNoteUpdate,
    repository: RepositoryDep,
) -> InvestmentNoteItem:
    note = repository.update_note(note_id, payload)
    if note is None:
        raise HTTPException(status_code=404, detail="Investment note not found")
    return note


@app.delete(f"{settings.api_prefix}/notes/{{note_id}}")
def delete_investment_note(
    note_id: int,
    repository: RepositoryDep,
) -> dict[str, bool]:
    if not repository.delete_note(note_id):
        raise HTTPException(status_code=404, detail="Investment note not found")
    return {"deleted": True}


@app.get(f"{settings.api_prefix}/sync-tasks")
def get_sync_tasks() -> dict[str, object]:
    return sync_job_runner.snapshot()


@app.get(f"{settings.api_prefix}/sync-tasks/{{task}}/history")
def get_sync_task_history(task: SyncTaskKey) -> dict[str, object]:
    return {"items": sync_job_runner.history(task)}


@app.post(f"{settings.api_prefix}/sync-tasks/{{task}}", status_code=202)
def start_sync_task(task: SyncTaskKey) -> dict[str, object]:
    try:
        return sync_job_runner.start(task)
    except SyncJobBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/{requested_path:path}", include_in_schema=False)
def frontend(requested_path: str) -> FileResponse:
    """Serve the production frontend and fall back to index.html for SPA routes."""
    if requested_path in DISABLED_DOCUMENTATION_PATHS:
        raise HTTPException(status_code=404, detail="Not found")
    if requested_path == settings.api_prefix.lstrip("/") or requested_path.startswith(
        f"{settings.api_prefix.lstrip('/')}/"
    ):
        raise HTTPException(status_code=404, detail="API route not found")

    dist_dir = FRONTEND_DIST_DIR.resolve()
    requested_file = (dist_dir / requested_path).resolve()
    if requested_path and requested_file.is_relative_to(dist_dir) and requested_file.is_file():
        response = FileResponse(requested_file)
        if requested_path.startswith("assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response

    index_file = dist_dir / "index.html"
    if index_file.is_file():
        return FileResponse(index_file, headers={"Cache-Control": "no-cache"})

    raise HTTPException(
        status_code=503,
        detail="Frontend build is missing; run `pnpm build` in frontend/.",
    )
