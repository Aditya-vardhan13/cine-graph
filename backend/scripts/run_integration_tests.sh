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
conda_env="${CINEGRAPH_CONDA_ENV:-cine-graph}"
conda_base="$(conda info --base)"
test_python="$conda_base/envs/$conda_env/bin/python"
if [ ! -x "$test_python" ]; then
  echo "Conda test interpreter not found: $test_python" >&2
  exit 1
fi

CINEGRAPH_RUN_INTEGRATION=1 \
CINEGRAPH_INTEGRATION_API_URL=http://127.0.0.1:8001 \
CINEGRAPH_TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5433/cinegraph_test \
PYTHONPATH=. "$test_python" -m pytest -m integration tests -q
