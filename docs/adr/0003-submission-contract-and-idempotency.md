# ADR 0003: Submission contract (202 Accepted) and idempotency keys

- Status: accepted (2026-10-28)
- Changes the API contract: `POST /api/v1/research` returned `201 Created`

## Context

Submitting research no longer completes anything synchronously; it accepts work. Clients (the browser, flaky mobile networks) retry POSTs, and a retried POST must not start a second paid research run.

## Decision

- `POST /api/v1/research` returns **`202 Accepted`** with the job body and a `Location: /api/v1/research/{id}` header.
- Optional `Idempotency-Key` header (1–128 chars). Stored on the job with a unique index on `(user_id, idempotency_key)`.
  - Same key + same payload → the original job is returned (`202`), no new row.
  - Same key + different payload → `409 Conflict`.
  - The payload is compared through a SHA-256 `request_fingerprint` of the normalised request.
  - A concurrent duplicate that loses the unique-index race catches the `IntegrityError` and returns the winner's job.
- The frontend generates one key per submit-form instance, so double-clicks and retries are safe.

## Alternatives

- **Keep 201**: semantically wrong, since nothing is complete when the response is sent.
- **Dedupe on (user, ticker, query) within N minutes**: guesses intent and blocks legitimate re-runs.
- **Separate idempotency table with stored responses** (Stripe style): more general, but we have one idempotent endpoint and the job row already is the response.

## Consequences

Tests updated from 201 to 202. Keys never expire for now; add a TTL if the table grows.

## Interview questions

1. *"201 vs 202?"* 201 means a resource was created as the result; 202 means accepted for processing that may not have happened yet.
2. *"Where does the client get the key?"* It generates one per user intent (form instance), not per HTTP attempt.
3. *"Two identical requests arrive at the same millisecond?"* The unique index decides; the loser catches the violation and returns the winner's row.
