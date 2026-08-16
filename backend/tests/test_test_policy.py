from pathlib import Path


FORBIDDEN_TEST_DOUBLES = (
    "monkeypatch",
    "unittest.mock",
    "Mock(",
    "MagicMock(",
    "responses.activate",
    "respx.mock",
)


def test_suite_does_not_use_mock_or_patch_frameworks() -> None:
    """Keep tests on retained payloads and real local infrastructure."""
    tests_root = Path(__file__).resolve().parent
    violations = [
        f"{path.relative_to(tests_root)}: {marker}"
        for path in tests_root.rglob("*.py")
        if path != Path(__file__)
        for marker in FORBIDDEN_TEST_DOUBLES
        if marker in path.read_text(encoding="utf-8")
    ]
    assert violations == []
