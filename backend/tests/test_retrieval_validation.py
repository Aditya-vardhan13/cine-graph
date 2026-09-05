from app.services.retrieval_validation import percentile


def test_percentile_interpolates_small_latency_samples() -> None:
    assert percentile([10.0, 20.0, 30.0], 0.5) == 20.0
    assert percentile([10.0, 20.0, 30.0], 0.95) == 29.0
    assert percentile([], 0.95) == 0.0
