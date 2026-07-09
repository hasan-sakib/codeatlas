#!/usr/bin/env bash
# Brings up the full dev stack and finishes the two steps Compose itself
# can't do: running migrations and bootstrapping the Qdrant collection.
# Idempotent — safe to re-run against an already-initialized stack.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ ! -f "${ROOT_DIR}/.env" ]; then
  cp "${ROOT_DIR}/.env.example" "${ROOT_DIR}/.env"
  SECRET=$(openssl rand -base64 32)
  python3 -c "
import re
path = '${ROOT_DIR}/.env'
with open(path) as f:
    content = f.read()
content = content.replace(
    'SECURITY__JWT_SECRET_KEY=changeme-generate-a-real-secret-for-any-non-local-env',
    'SECURITY__JWT_SECRET_KEY=${SECRET}',
)
with open(path, 'w') as f:
    f.write(content)
"
  echo "Created .env with a generated JWT secret."
fi

if [ ! -f "${ROOT_DIR}/frontend/.env" ]; then
  cp "${ROOT_DIR}/frontend/.env.example" "${ROOT_DIR}/frontend/.env"
  SECRET=$(openssl rand -base64 32)
  python3 -c "
import re
path = '${ROOT_DIR}/frontend/.env'
with open(path) as f:
    content = f.read()
content = re.sub(r'SESSION_SECRET=.*', f'SESSION_SECRET=${SECRET}', content)
with open(path, 'w') as f:
    f.write(content)
"
  echo "Created frontend/.env with a generated session secret."
fi

cd "${ROOT_DIR}/infra/docker"
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build

echo "Waiting for backend-api to become healthy..."
for _ in $(seq 1 60); do
  if curl -sf http://localhost:8000/health/ready >/dev/null 2>&1; then
    break
  fi
  sleep 5
done

echo "Running migrations..."
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec -T backend-api alembic upgrade head

echo "Bootstrapping Qdrant collection (skips if it already exists)..."
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec -T backend-api python -c "
import asyncio
from qdrant_client import AsyncQdrantClient
from app.infrastructure.vectorstore.collection_schema import create_versioned_collection, point_alias_to, alias_name
from app.core.config import get_settings

async def main():
    settings = get_settings()
    client = AsyncQdrantClient(url=str(settings.qdrant.url))
    try:
        name = await create_versioned_collection(client, prefix=settings.qdrant.collection_prefix, version=1, embedding_dim=1024)
        await point_alias_to(client, alias_name(settings.qdrant.collection_prefix), name)
        print(f'Bootstrapped {name}')
    except Exception as exc:
        if '409' in str(exc) or 'already exists' in str(exc):
            print('Collection already exists — skipping.')
        else:
            raise
    finally:
        await client.close()

asyncio.run(main())
"

cat <<'EOF'

Stack is up:
  Frontend:  http://localhost:3000
  Backend:   http://localhost:8000
  API docs:  http://localhost:8000/docs
  Metrics:   http://localhost:8000/metrics
  Readiness: http://localhost:8000/health/ready

Register an account at http://localhost:3000/register to get started.
Chat responses need a real model pulled into the ollama container, e.g.:
  docker compose -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.dev.yml exec ollama ollama pull qwen3:4b
EOF
