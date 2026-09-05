from app.services.lexical_retrieval import Bm25Index, reciprocal_rank_fusion, weighted_reciprocal_rank_fusion


def test_bm25_prioritises_specific_lexical_evidence() -> None:
    index = Bm25Index.build([
        "Batman confronts the Joker in Gotham.",
        "A family returns home after a difficult journey.",
        "The Joker forces Gotham to make an impossible choice.",
    ])

    assert index.rank("What impossible choice does the Joker force Gotham to make?", cutoff=2) == [2, 0]


def test_rrf_combines_rankings_without_comparing_raw_scores() -> None:
    assert reciprocal_rank_fusion([["a", "b"], ["b", "c"]], cutoff=3, constant=1) == ["b", "a", "c"]


def test_weighted_rrf_preserves_the_declared_primary_ranker() -> None:
    result = weighted_reciprocal_rank_fusion(
        [(["semantic", "shared"], 3.0), (["lexical", "shared"], 1.0)],
        cutoff=3,
        constant=1,
    )

    assert result == ["semantic", "shared", "lexical"]
