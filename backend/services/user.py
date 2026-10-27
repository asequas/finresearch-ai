from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.models.user import User

DEV_USER_EMAIL = "dev@finresearch.local"


class UserService:
    def get_or_create_dev_user(self, session: Session) -> User:
        """Race-safe: concurrent first requests both end up with the same row."""
        user = session.scalar(select(User).where(User.email == DEV_USER_EMAIL))
        if user is not None:
            return user

        session.execute(
            insert(User).values(email=DEV_USER_EMAIL).on_conflict_do_nothing(index_elements=["email"])
        )
        session.commit()
        return session.scalar(select(User).where(User.email == DEV_USER_EMAIL))
