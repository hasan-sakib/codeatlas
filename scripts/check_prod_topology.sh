#!/usr/bin/env bash
# Asserts the prod Compose topology invariant from DESIGN.md §22: only
# `frontend`/`backend-api` publish host ports, and `backend_net` is
# internal. Run after touching any infra/docker/*.yml file.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}/infra/docker"

CONFIG_JSON=$(docker compose -f docker-compose.yml -f docker-compose.prod.yml config --format json)

ALLOWED_PORTS_SERVICES="backend-api frontend"
FAILED=0

for service in $(echo "${CONFIG_JSON}" | jq -r '.services | keys[]'); do
  has_ports=$(echo "${CONFIG_JSON}" | jq ".services[\"${service}\"].ports // [] | length > 0")
  if [ "${has_ports}" = "true" ]; then
    if ! echo "${ALLOWED_PORTS_SERVICES}" | grep -qw "${service}"; then
      echo "FAIL: service '${service}' publishes a host port in the prod overlay but isn't in the allowed list (${ALLOWED_PORTS_SERVICES})"
      FAILED=1
    fi
  fi
done

is_internal=$(echo "${CONFIG_JSON}" | jq '.networks.backend_net.internal // false')
if [ "${is_internal}" != "true" ]; then
  echo "FAIL: backend_net is not marked internal: true in the prod overlay"
  FAILED=1
fi

if [ "${FAILED}" -eq 0 ]; then
  echo "OK: prod topology invariant holds (only ${ALLOWED_PORTS_SERVICES} publish ports; backend_net is internal)"
fi

exit "${FAILED}"
