from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.api.dependencies import (
    get_current_user,
    get_db,
    get_research_job_service,
)
from backend.models.user import User
from backend.schemas.research import ResearchCreateRequest, ResearchJobResponse
from backend.services.research_job import ResearchJobService


router = APIRouter(
    prefix="/api/v1/research",
    tags=["research"],
)


@router.post(
    "",
    response_model=ResearchJobResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_research_job(
    request: ResearchCreateRequest,
    db: Session = Depends(get_db),
    service: ResearchJobService = Depends(get_research_job_service),
    current_user: User = Depends(get_current_user),
):
    return service.create_research_job(
        db,
        user_id=current_user.id,
        request=request,
    )