from app.services.wikipedia_text_v2 import readable_wikitext as read_v2
from app.services.wikipedia_text_v3 import derive_passages, readable_wikitext


def test_versioned_parser_preserves_language_template_display_text():
    raw = "After forcing the current {{lang|it|[[prima ballerina]]}}, Beth, into retirement."
    assert read_v2(raw).text == "After forcing the current , Beth, into retirement."
    assert readable_wikitext(raw).text == "After forcing the current prima ballerina, Beth, into retirement."


def test_nested_references_are_retained_verbatim_and_not_promoted_to_prose():
    raw = "Visible {{lang|te|తెలుగు}}.<ref name='source'>{{lang|it|unseen}}</ref>"
    parsed = readable_wikitext(raw)
    assert parsed.text == "Visible తెలుగు."
    assert parsed.removed_citations == ("<ref name='source'>{{lang|it|unseen}}</ref>",)


def test_template_only_paragraph_is_not_dropped_during_chunking():
    passages = derive_passages("== Plot ==\n{{lang|it|[[prima ballerina]]}}")
    assert [p.content for p in passages] == ["prima ballerina"]


def test_caption_only_section_is_preserved_separately():
    passages = derive_passages("== Production ==\n[[File:Test.jpg|thumb|A useful caption.]]")
    assert [(p.section_title, p.content) for p in passages] == [("Production / Image caption", "A useful caption.")]


def test_unrecognized_or_incomplete_templates_are_not_invented():
    assert readable_wikitext("Before {{lang|en}} and {{unknown|hidden}} after.").text == "Before and after."
