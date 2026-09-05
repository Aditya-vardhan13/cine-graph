from app.services.hybrid_evidence_retrieval import _fused_scores, lexical_tsquery


def test_fused_scores_reward_candidates_supported_by_both_methods() -> None:
    scores = _fused_scores((["semantic", "shared"], ["shared", "lexical"]), constant=1)

    assert scores["shared"] > scores["semantic"]
    assert scores["shared"] > scores["lexical"]


def test_lexical_query_uses_safe_content_terms_with_or_semantics() -> None:
    assert lexical_tsquery("How does Bowman overcome HAL after the lockout?") == (
        "bowman | overcome | hal | after | lockout"
    )
