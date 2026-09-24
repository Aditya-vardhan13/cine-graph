from app.services.wikipedia_revision_recovery import recovery_target_is_valid, should_retry_response


def test_recovery_requires_exact_revision_page_and_nonempty_text() -> None:
    page = {"parse": {"revid": 123, "pageid": 456, "wikitext": "A film article."}}
    assert recovery_target_is_valid(page, revision="123", external_id="enwiki:456")
    assert not recovery_target_is_valid(page, revision="124", external_id="enwiki:456")
    assert not recovery_target_is_valid(page, revision="123", external_id="enwiki:457")
    assert not recovery_target_is_valid({"parse": {**page["parse"], "wikitext": "  "}}, revision="123", external_id="enwiki:456")
    assert not recovery_target_is_valid({"error": {"code": "maxlag"}}, revision="123", external_id="enwiki:456")


def test_recovery_retries_only_explicit_throttling_or_lag() -> None:
    assert should_retry_response(429, {"Retry-After": "12"}, None)
    assert should_retry_response(200, {}, "maxlag")
    assert should_retry_response(503, {"X-Database-Lag": "8"}, None)
    assert not should_retry_response(503, {}, None)
    assert not should_retry_response(502, {}, None)
    assert not should_retry_response(403, {}, None)
