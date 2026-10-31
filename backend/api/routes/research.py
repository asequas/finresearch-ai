from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy.orm import Session

from backend.api.dependencies import (
    get_current_user,
    get_db,
    get_research_job_service,
)
from backend.models.research_job import ResearchJobStatus
from backend.models.user import User
from backend.schemas.research import (
    ResearchCreateRequest,
    ResearchJobDetailResponse,
    ResearchJobListResponse,
    ResearchJobResponse,
)
from backend.schemas.agent import AgentTraceResponse, ChatQuestion, ChatThreadResponse
from backend.schemas.report import CompanyDetail, CompanySummary, ReportResponse
from backend.services.agent_trace import AgentTraceService
from backend.services.analyst_chat import AnalystChatService
from backend.services.valuation import ValuationService
from backend.schemas.valuation import ValuationOut, WhatIfRequest
from backend.services.report import ReportService
from backend.services.research_job import ResearchJobService


router = APIRouter(
    prefix="/api/v1/research",
    tags=["research"],
)


@router.post(
    "",
    response_model=ResearchJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={409: {"description": "Idempotency-Key reused with a different request"}},
)
def create_research_job(
    request: ResearchCreateRequest,
    response: Response,
    idempotency_key: str | None = Header(default=None, min_length=1, max_length=128),
    db: Session = Depends(get_db),
    service: ResearchJobService = Depends(get_research_job_service),
    current_user: User = Depends(get_current_user),
):
    job = service.submit(
        db,
        user_id=current_user.id,
        request=request,
        idempotency_key=idempotency_key,
    )
    response.headers["Location"] = f"/api/v1/research/{job.id}"
    return job


@router.get(
    "",
    response_model=ResearchJobListResponse,
)
def list_research_jobs(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    status_filter: ResearchJobStatus | None = Query(default=None, alias="status"),
    ticker: str | None = Query(default=None, max_length=20),
    db: Session = Depends(get_db),
    service: ResearchJobService = Depends(get_research_job_service),
    current_user: User = Depends(get_current_user),
):
    return service.list_jobs(
        db,
        user_id=current_user.id,
        limit=limit,
        cursor=cursor,
        status=status_filter,
        ticker=ticker,
    )


@router.get(
    "/{job_id}",
    response_model=ResearchJobDetailResponse,
    responses={404: {"description": "Research job not found"}},
)
def get_research_job(
    job_id: UUID,
    db: Session = Depends(get_db),
    service: ResearchJobService = Depends(get_research_job_service),
    current_user: User = Depends(get_current_user),
):
    return service.get_detail(db, job_id=job_id, user_id=current_user.id)


@router.post(
    "/{job_id}/cancel",
    response_model=ResearchJobResponse,
    responses={404: {"description": "Not found"}, 409: {"description": "Job cannot be cancelled"}},
)
def cancel_research_job(
    job_id: UUID,
    db: Session = Depends(get_db),
    service: ResearchJobService = Depends(get_research_job_service),
    current_user: User = Depends(get_current_user),
):
    return service.cancel(db, job_id=job_id, user_id=current_user.id)


@router.post(
    "/{job_id}/retry",
    response_model=ResearchJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={404: {"description": "Not found"}, 409: {"description": "Job cannot be retried"}},
)
def retry_research_job(
    job_id: UUID,
    db: Session = Depends(get_db),
    service: ResearchJobService = Depends(get_research_job_service),
    current_user: User = Depends(get_current_user),
):
    return service.retry(db, job_id=job_id, user_id=current_user.id)


@router.get(
    "/{job_id}/report",
    response_model=ReportResponse,
    responses={404: {"description": "Job not found or report not ready"}},
)
def get_research_report(
    job_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ReportService().get_report(db, job_id=job_id, user_id=current_user.id)


@router.get(
    "/{job_id}/trace",
    response_model=AgentTraceResponse,
    responses={404: {"description": "Research job not found"}},
)
def get_research_trace(
    job_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """What the research agent did: its plan, each researcher's tool calls, and the critic's decisions."""
    return AgentTraceService().get_trace(db, job_id=job_id, user_id=current_user.id)


@router.get(
    "/{job_id}/valuation",
    response_model=ValuationOut,
    responses={404: {"description": "Job not found or not valued yet"}},
)
def get_valuation(
    job_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The job's DCF intrinsic value: every assumption with its source, the projection, bridge and sensitivity."""
    return ValuationService().get(db, job_id=job_id, user_id=current_user.id)


@router.post(
    "/{job_id}/valuation/what-if",
    response_model=ValuationOut,
    responses={400: {"description": "The assumptions break the model's constraints"}, 404: {"description": "Not found"}},
)
def valuation_what_if(
    job_id: UUID,
    body: WhatIfRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Recompute the DCF with some assumptions changed. Deterministic, saves nothing, no AI."""
    return ValuationService().what_if(db, job_id=job_id, user_id=current_user.id, request=body)


def get_chat_service() -> AnalystChatService:
    return AnalystChatService()


@router.get(
    "/{job_id}/chat",
    response_model=ChatThreadResponse,
    responses={404: {"description": "Job not found or report not ready"}},
)
def get_analyst_chat(
    job_id: UUID,
    db: Session = Depends(get_db),
    service: AnalystChatService = Depends(get_chat_service),
    current_user: User = Depends(get_current_user),
):
    return service.get_thread(db, job_id=job_id, user_id=current_user.id)


@router.post(
    "/{job_id}/chat",
    response_model=ChatThreadResponse,
    responses={
        404: {"description": "Job not found or report not ready"},
        429: {"description": "This report's question limit is used up"},
        503: {"description": "The model provider is busy; retry shortly"},
    },
)
def ask_analyst(
    job_id: UUID,
    body: ChatQuestion,
    db: Session = Depends(get_db),
    service: AnalystChatService = Depends(get_chat_service),
    current_user: User = Depends(get_current_user),
):
    """Ask a follow-up question about a finished report. Answers cite filing passages, each quote checked."""
    return service.ask(db, job_id=job_id, user_id=current_user.id, question=body.question)


companies_router = APIRouter(prefix="/api/v1/companies", tags=["companies"])


@companies_router.get("", response_model=list[CompanySummary])
def list_companies(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ReportService().list_companies(db, user_id=current_user.id)


@companies_router.get(
    "/{ticker}",
    response_model=CompanyDetail,
    responses={404: {"description": "No research on this company yet"}},
)
def get_company(
    ticker: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ReportService().get_company(db, ticker=ticker, user_id=current_user.id)
