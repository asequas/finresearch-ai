#!/usr/bin/env bash
# Smoke-test a running stack through its public entry point.
#   deploy/smoke.sh http://localhost          health, UI and API only
#   deploy/smoke.sh http://localhost --job    also run one research job to completion (needs PIPELINE=stub)
set -euo pipefail
BASE="${1:?usage: smoke.sh BASE_URL [--job]}"

for _ in $(seq 1 60); do
  curl -fsS "$BASE/health" >/dev/null 2>&1 && break
  sleep 2
done
curl -fsS "$BASE/health" | grep -q '"ok"' || { echo "health check failed"; exit 1; }
curl -fsS "$BASE/" | grep -q '<div id="root">' || { echo "UI not served"; exit 1; }
curl -fsS "$BASE/api/v1/research?limit=1" >/dev/null || { echo "API not reachable through the web server"; exit 1; }
echo "health, UI and API: ok"

[ "${2:-}" = "--job" ] || exit 0
id=$(curl -fsS -X POST "$BASE/api/v1/research" -H 'Content-Type: application/json' \
  -H "Idempotency-Key: smoke-$(date +%s)" \
  -d '{"query":"Smoke test","company":"Smoke Test Inc.","ticker":"SMOKE"}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
for _ in $(seq 1 90); do
  status=$(curl -fsS "$BASE/api/v1/research/$id" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')
  case "$status" in
    completed) echo "research job $id: completed"; exit 0 ;;
    failed|cancelled) echo "research job $id: $status"; exit 1 ;;
  esac
  sleep 2
done
echo "research job $id: still $status after 3 minutes"; exit 1
