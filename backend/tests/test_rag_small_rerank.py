import pytest

from app.services.rag_small_rerank import aggregate_windows


def test_window_aggregation_preserves_every_candidate_and_best_anchor():
    pool = [{"chunk_id": key, "section_title": "Plot"} for key in ("A", "B")]
    windows = [{"chunk_id": "A", "start": 0}, {"chunk_id": "A", "start": 4}, {"chunk_id": "B", "start": 0}]
    ranked = aggregate_windows(pool, windows, [0., 2., 1.])
    assert [row["chunk_id"] for row in ranked] == ["A", "B"]
    assert ranked[0]["winning_window"]["start"] == 4
    with pytest.raises(ValueError, match="finite"):
        aggregate_windows(pool, windows, [0., float("nan"), 1.])
    with pytest.raises(ValueError, match="Every candidate"):
        aggregate_windows(pool, windows[:2], [0., 2.])
