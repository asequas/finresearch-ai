from fastapi import Depends
from sqlalchemy.orm import Session

from backend.core.database import SessionLocal
from backend.models.user import User
from backend.repositories.research_job import ResearchJobRepository
from backend.services.research_job import ResearchJobService


def get_db():
    with SessionLocal() as session:
        yield session


def get_research_job_service() -> ResearchJobService:
    return ResearchJobService(
        repository=ResearchJobRepository()
    )


def get_current_user(
    db: Session = Depends(get_db),
) -> User:
    email = "dev@finresearch.local"

    user = db.query(User).filter(User.email == email).first()

    if user is None:
        user = User(email=email)
        db.add(user)
        db.commit()
        db.refresh(user)

    return user