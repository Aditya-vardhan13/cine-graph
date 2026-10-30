"""Pure retained-wikitext regression cases; no network, database or mocking."""
from app.services.wikipedia_text_v2 import EXTRACTION_VERSION, chunk_section_v2, readable_wikitext


def test_nested_file_caption_is_not_mistaken_for_film_narrative() -> None:
    source = (
        "Batman confronts [[Joker (character)|the Joker]]. "
        "[[File:Gotham.jpg|thumb|alt=Gotham with [[Batman]]|A [[Batman|hero]] watches.]] "
        "Dent faces a choice.<ref name=ending>Source citation.</ref>"
    )
    result = readable_wikitext(source)
    assert result.text == "Batman confronts the Joker. Dent faces a choice."
    assert len(result.removed_media) == 1
    assert result.removed_media[0].startswith("[[File:Gotham.jpg")
    assert result.media_captions == ("A hero watches.",)
    assert len(result.removed_citations) == 1
    assert "name=ending" in result.removed_citations[0]


def test_nested_templates_links_and_gallery_are_separate_from_prose() -> None:
    source = (
        "The choice follows [[Rachel Dawes|Rachel]]'s death. "
        "{{cite web|title={{lang|en|Critical response}}}} "
        "<gallery>File:Still.jpg|A visual caption</gallery> "
        "The ending changes Gotham.&nbsp;"
    )
    result = readable_wikitext(source)
    assert result.text == "The choice follows Rachel's death. The ending changes Gotham."
    assert len(result.removed_citations) == 1
    assert "gallery" in result.removed_citations[0]
    assert EXTRACTION_VERSION.endswith("v2")


def test_media_caption_with_nested_links_keeps_nonvisual_source_statement_separate() -> None:
    source = (
        "[[File:Wall-E lighting.png|thumb|left|alt=WALL-E holding a bra|"
        "[[WALL-E (character)|WALL-E]] finds a bra. [[Roger Deakins]] and "
        "[[Dennis Muren]] were consulted on realistic lighting.]]"
    )
    result = readable_wikitext(source)
    assert result.text == ""
    assert result.media_captions == (
        "WALL-E finds a bra. Roger Deakins and Dennis Muren were consulted on realistic lighting.",
    )


def test_paragraph_boundary_inside_reference_does_not_fragment_wikitext() -> None:
    source = (
        "A film won an award.<ref>{{cite web\n |title=Award ballot\n\n"
        " |url=https://example.org/ballot\n}}</ref> The second sentence follows.\n\n"
        "Another paragraph begins."
    )
    chunks = list(chunk_section_v2(source, limit=40))
    assert len(chunks) == 2
    assert "</ref>" in chunks[0]
    assert readable_wikitext(chunks[0]).text == (
        "A film won an award. The second sentence follows."
    )
    assert readable_wikitext(chunks[1]).text == "Another paragraph begins."


def test_file_page_link_keeps_display_label_without_raw_markup() -> None:
    result = readable_wikitext("The poster, known as [[:File:Poster.jpg|''Style 'A''']], depicts the hero.")
    assert result.text == "The poster, known as Style 'A', depicts the hero."
    assert result.removed_media == ()
