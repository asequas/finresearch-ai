from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.api.dependencies import get_current_user, get_db
from backend.models.user import User
from backend.schemas.costs import CostSummary
from backend.services.costs import CostService

router = APIRouter(prefix="/api/v1/costs", tags=["costs"])


@router.get("", response_model=CostSummary)
def get_costs(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """What the AI calls have cost: billed spend against the caps, and list-price usage by day, model, stage and job.

    Spend is per deployment (one Gemini project), not per user.
    """
    return CostService().summary(db, days=days)
