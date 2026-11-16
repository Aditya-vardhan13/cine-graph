"""Keep isolated database fixtures bounded to the test that created them."""
import pytest

from tests.postgres_test_db import cleanup_created_test_schemas


@pytest.fixture(autouse=True)
def cleanup_test_database_schemas():
    yield
    cleanup_created_test_schemas()
