"""Start-up checks that turn a stopped database or missing key into a clear sentence.

Run: python -m backend.core.preflight   (exit code 1 if anything blocks research jobs)
"""
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from backend.core.config import settings

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def _migration_head() -> str | None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "database" / "migrations"))
    return ScriptDirectory.from_config(config).get_current_head()


def run_checks() -> list[Check]:
    from backend.core.database import engine

    checks: list[Check] = []
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        checks.append(Check("database", True, "PostgreSQL is reachable."))
        head = _migration_head()
        checks.append(
            Check(
                "migrations",
                revision == head,
                "Schema is up to date." if revision == head
                else f"Database is at {revision}, code expects {head}. Run: alembic upgrade head",
            )
        )
    except OperationalError:
        checks.append(
            Check("database", False, "PostgreSQL is not reachable. Start Docker Desktop, then: docker compose up -d")
        )
    checks.append(
        Check(
            "gemini",
            bool(settings.gemini_api_key),
            "Gemini API key is set." if settings.gemini_api_key else "GEMINI_API_KEY is missing from .env.",
        )
    )
    sec_ok = bool(settings.sec_user_agent and "@" in settings.sec_user_agent)
    checks.append(
        Check("sec", sec_ok, "SEC contact email is set." if sec_ok else "SEC_USER_AGENT (a contact email) is missing from .env.")
    )
    return checks


def main() -> int:
    checks = run_checks()
    for check in checks:
        print(f"  {'ok ' if check.ok else 'FIX'}  {check.name:<11} {check.detail}")
    return 0 if all(c.ok for c in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
