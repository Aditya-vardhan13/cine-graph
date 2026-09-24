from app.services.evidence_coverage import section_categories


def test_section_categories_are_only_heading_proxies() -> None:
    assert section_categories("Production / Writing", "Writing") == ("production", "writing_craft")
    assert section_categories("Themes and analysis / Terrorism", "Terrorism") == ("themes_analysis",)
    assert section_categories("Reception / Critical response", "Critical response") == ("reception",)
    assert section_categories("Plot", "Plot") == ("plot",)
    assert section_categories("Other releases", "Home media") == ()
