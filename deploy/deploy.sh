#!/usr/bin/env bash
# Run on the server from the directory holding docker-compose.yml and .env:
#   ./deploy.sh sha-abc123
# Pulls the tag, migrates, restarts, smoke-tests, and rolls back to the previous tag if the smoke test fails.
set -euo pipefail
cd "$(dirname "$0")"
TAG="${1:?usage: deploy.sh IMAGE_TAG}"
PREVIOUS="$(cat .deployed-tag 2>/dev/null || true)"
PORT="$(grep -E '^WEB_PORT=' .env 2>/dev/null | cut -d= -f2 || true)"
URL="http://localhost:${PORT:-80}"

echo "Deploying $TAG (previous: ${PREVIOUS:-none})"
IMAGE_TAG="$TAG" docker compose pull --quiet
IMAGE_TAG="$TAG" docker compose up -d --remove-orphans

if ./smoke.sh "$URL"; then
  echo "$TAG" > .deployed-tag
  docker image prune -f >/dev/null
  echo "Deployed $TAG"
  exit 0
fi

echo "Smoke test failed for $TAG" >&2
if [ -n "$PREVIOUS" ]; then
  echo "Rolling back to $PREVIOUS" >&2
  IMAGE_TAG="$PREVIOUS" docker compose up -d --remove-orphans
  ./smoke.sh "$URL" && echo "Rolled back to $PREVIOUS" >&2
fi
exit 1
