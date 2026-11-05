import pytest
from pydantic import ValidationError

from app.core.config import Settings


@pytest.mark.parametrize("environment", ["development", "local"])
def test_noncommercial_sources_are_explicit_local_opt_in(environment: str) -> None:
    assert Settings(_env_file=None, environment=environment, serve_noncommercial_sources=True).serve_noncommercial_sources
    assert not Settings(_env_file=None, environment=environment, serve_noncommercial_sources=False).serve_noncommercial_sources


@pytest.mark.parametrize("environment", ["production", "staging", "test", "Development"])
def test_noncommercial_sources_rejected_outside_local_scope(environment: str) -> None:
    with pytest.raises(ValidationError, match="restricted to local development"):
        Settings(_env_file=None, environment=environment, serve_noncommercial_sources=True)
    assert not Settings(_env_file=None, environment=environment, serve_noncommercial_sources=False).serve_noncommercial_sources
