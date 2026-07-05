#!/usr/bin/env bash
# Local dev bootstrap: install backend deps, install git hooks, seed .env.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ ! -f "${ROOT_DIR}/.env" ]; then
  cp "${ROOT_DIR}/.env.example" "${ROOT_DIR}/.env"
  echo "Created .env from .env.example — review values before running services."
fi

cd "${ROOT_DIR}/backend"
uv sync --all-groups
uv run pre-commit install --config "${ROOT_DIR}/.pre-commit-config.yaml"

echo "Bootstrap complete. Run 'docker compose -f infra/docker/docker-compose.yml up' to start services."
