#!/usr/bin/env bash
# Poll a host:port until it accepts TCP connections or the timeout elapses.
# Usage: wait-for-services.sh host:port [host:port ...] -- command args...
set -euo pipefail

TIMEOUT_SECONDS=60
TARGETS=()

while [[ $# -gt 0 && "$1" != "--" ]]; do
  TARGETS+=("$1")
  shift
done
[[ "${1:-}" == "--" ]] && shift

for target in "${TARGETS[@]}"; do
  host="${target%%:*}"
  port="${target##*:}"
  echo "Waiting for ${host}:${port}..."
  elapsed=0
  until (echo > "/dev/tcp/${host}/${port}") 2>/dev/null; do
    sleep 1
    elapsed=$((elapsed + 1))
    if [ "${elapsed}" -ge "${TIMEOUT_SECONDS}" ]; then
      echo "Timed out waiting for ${host}:${port}" >&2
      exit 1
    fi
  done
  echo "${host}:${port} is up."
done

if [ "$#" -gt 0 ]; then
  exec "$@"
fi
