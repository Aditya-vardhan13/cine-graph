#!/bin/sh
set -eu

compose_file="../docker-compose.integration.yml"

docker compose -f "$compose_file" up --build -d

attempt=0
until curl -fsS http://127.0.0.1:8001/health >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 30 ]; then
    docker compose -f "$compose_file" logs api-test db-test
    exit 1
  fi
  sleep 1
done

docker compose -f "$compose_file" exec -T api-test env PYTHONPATH=/app python scripts/seed_integration_fixture.py
CINEGRAPH_RUN_INTEGRATION=1 \
CINEGRAPH_INTEGRATION_API_URL=http://127.0.0.1:8001 \
CINEGRAPH_TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5433/cinegraph_test \
PYTHONPATH=. conda run -n "${CINEGRAPH_CONDA_ENV:-cine-graph}" python -m pytest -m integration tests -q
