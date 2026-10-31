#!/usr/bin/env bash
# CI: start the production compose stack from locally built images and run one stub research job through it.
# No external services and no model calls (PIPELINE=stub, RERANKER=none, PRICE_SOURCE=none, no Gemini key).
set -euo pipefail
cd "$(dirname "$0")"
TAG="${1:?usage: ci-smoke.sh IMAGE_TAG}"
cat > .env <<ENV
POSTGRES_PASSWORD=ci-only-password
PIPELINE=stub
STUB_STAGE_SECONDS=0.2
RERANKER=none
PRICE_SOURCE=none
GEMINI_API_KEY=
WEB_PORT=8080
ENV
export REGISTRY="${REGISTRY:-local}" IMAGE_TAG="$TAG"
trap 'docker compose logs --no-color --tail 80 || true; docker compose down -v >/dev/null 2>&1 || true; rm -f .env' EXIT
docker compose up -d
./smoke.sh http://localhost:8080 --job
