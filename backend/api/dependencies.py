from collections.abc import Iterator

from fastapi import Depends
from sqlalchemy.orm import Session

from backend.core.database import SessionLocal
from backend.models.user import User
from backend.repositories.research_job import ResearchJobRepository
from backend.services.research_job import ResearchJobService
from backend.services.user import UserService


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


def get_research_job_service() -> ResearchJobService:
    return ResearchJobService(
        repository=ResearchJobRepository()
    )


def get_current_user(
    db: Session = Depends(get_db),
) -> User:
    # Development identity until real auth lands (Phase 7). Every read is
    # already scoped to this user, so swapping in real auth changes only this function.
    return UserService().get_or_create_dev_user(db)
