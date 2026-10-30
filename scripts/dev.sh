#!/usr/bin/env bash
# Start the whole app locally: database, migrations, API, one worker and the UI.
# Usage: scripts/dev.sh        (Ctrl-C stops everything it started)
set -euo pipefail
cd "$(dirname "$0")/.."

LOGS=.cache/logs
mkdir -p "$LOGS"

if ! docker info >/dev/null 2>&1; then
  echo "Docker isn't running. Starting Docker Desktop…"
  open -a Docker 2>/dev/null || { echo "Start Docker, then run this again."; exit 1; }
  for _ in $(seq 1 60); do docker info >/dev/null 2>&1 && break; sleep 2; done
  docker info >/dev/null 2>&1 || { echo "Docker didn't start within two minutes."; exit 1; }
fi

docker compose up -d >/dev/null 2>&1
printf "Waiting for PostgreSQL"
for _ in $(seq 1 30); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' finresearch-postgres 2>/dev/null)" = healthy ] && break
  printf "."; sleep 2
done
echo

[ -d .venv ] || { echo "No .venv found. See README → Run it locally."; exit 1; }
# shellcheck disable=SC1091
source .venv/bin/activate
alembic upgrade head >/dev/null 2>&1 || { echo "Migrations failed. Run: alembic upgrade head"; exit 1; }

echo "Preflight:"
python -m backend.core.preflight || echo "Research jobs will fail until the items marked FIX are resolved."

pids=()
cleanup() { echo; echo "Stopping…"; kill "${pids[@]}" 2>/dev/null || true; wait 2>/dev/null || true; }
trap cleanup INT TERM EXIT

uvicorn backend.main:app --port 8000 >"$LOGS/api.log" 2>&1 & pids+=($!)
python -m backend.worker.main >"$LOGS/worker.log" 2>&1 & pids+=($!)
(cd frontend && npm run dev -- --port 5173 --strictPort >"../$LOGS/ui.log" 2>&1) & pids+=($!)

echo
echo "FinResearch is starting:"
echo "  UI      http://localhost:5173"
echo "  API     http://127.0.0.1:8000/docs"
echo "  Logs    $LOGS/{api,worker,ui}.log"
echo "Press Ctrl-C to stop."
wait
