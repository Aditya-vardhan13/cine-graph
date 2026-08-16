from app.services.evidence_preprocessing import ChunkConfiguration, chunk_passage, normalize_content


def test_sentence_chunking_is_deterministic_and_keeps_sentence_overlap() -> None:
    configuration = ChunkConfiguration(target_tokens=10, maximum_tokens=13, overlap_tokens=3, minimum_words=1)
    chunks = chunk_passage(
        "Alpha arrives at the station. Beta waits under rain. Gamma hears a distant horn. "
        "Delta calls the driver. Epsilon boards the train.",
        config=configuration,
    )

    assert [(chunk.ordinal, chunk.token_count_estimate) for chunk in chunks] == [(0, 11), (1, 11), (2, 11), (3, 10)]
    assert chunks[0].content.endswith("Beta waits under rain.")
    assert chunks[1].content.startswith("Beta waits under rain.")
    assert all(chunk.quality_status == "eligible" for chunk in chunks)


def test_preprocessing_marks_short_and_oversized_evidence_without_losing_it() -> None:
    short = chunk_passage("Brief evidence only.", config=ChunkConfiguration(minimum_words=10))[0]
    enormous_sentence = chunk_passage(
        " ".join(["Word"] * 370) + ".",
        config=ChunkConfiguration(target_tokens=300, maximum_tokens=360, overlap_tokens=50, minimum_words=1),
    )[0]

    assert short.quality_status == "excluded"
    assert short.quality_flags == ("below_minimum_words",)
    assert enormous_sentence.quality_status == "excluded"
    assert enormous_sentence.quality_flags == ("oversized_single_sentence",)
    assert normalize_content("a\u00a0 b\n c") == "a b c"


def test_overlap_never_pushes_an_eligible_chunk_past_the_hard_maximum() -> None:
    configuration = ChunkConfiguration(target_tokens=10, maximum_tokens=12, overlap_tokens=5, minimum_words=1)
    chunks = chunk_passage(
        "One two three four five six seven. Eight nine ten eleven twelve thirteen fourteen.",
        config=configuration,
    )

    assert len(chunks) == 2
    assert all(chunk.quality_status == "eligible" for chunk in chunks)
    assert all(chunk.token_count_estimate <= configuration.maximum_tokens for chunk in chunks)
