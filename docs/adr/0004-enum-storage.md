# ADR 0004: Store enums as VARCHAR + CHECK constraints

- Status: accepted (2026-10-28)

## Context

`research_jobs.status` was `VARCHAR(32)` with no constraint, and `current_stage` was a free string. The audit inserted `'banana'` and `'not_a_stage'`; the next read crashed or returned 500. `alembic check` looked clean only because `env.py` suppressed the type comparison.

## Decision

Enum-like columns are `VARCHAR(n)` with a named CHECK constraint listing the allowed values. On the ORM side they're mapped with SQLAlchemy `Enum(native_enum=False, length=n)`, so Python sees enum members. The `env.py` exemption is removed.

## Alternatives

- **Native PostgreSQL `ENUM`**: strict and compact, but adding or renaming values needs `ALTER TYPE`, which has had transaction restrictions and is awkward in Alembic autogenerate. Removing a value isn't supported at all.
- **Lookup tables with FKs**: the most flexible, but a join for every read and more ceremony than nine stage names deserve.

## Consequences

Changing allowed values means a migration that drops and recreates the CHECK constraint. That's cheap and explicit. The application and the database both reject bad values.

## Interview question

*"Why not trust the application to validate?"* Not all writes go through the app (psql, scripts, future services, bugs). The database is the last line of defence and the only one every writer goes through.
