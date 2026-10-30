"""Versioned derivative identity and caption separation, without network or mocks."""
from app.services.wikipedia_passages_v2 import derive_passages


def test_v2_passages_keep_prose_and_image_caption_distinct() -> None:
    article = (
        "Lead introduces the film.\n"
        "== Plot ==\n"
        "Batman confronts [[Joker (character)|the Joker]].\n\n"
        "[[File:Gotham.jpg|thumb|A [[Batman|hero]] watches the city.]]\n\n"
        "Dent faces a choice.<ref name=ending>Source citation.</ref>"
    )
    passages = derive_passages(article)
    assert [(item.section_locator, item.ordinal) for item in passages] == [
        ("lead", 0), ("plot", 0), ("plot/media-caption", 0),
    ]
    assert passages[1].content == "Batman confronts the Joker. Dent faces a choice."
    assert passages[2].content == "A hero watches the city."
    assert passages[1].citation_markers == ("ending",)
