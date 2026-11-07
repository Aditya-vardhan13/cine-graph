"""Small file-backed contract tests for the local CMU discovery manifest."""
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_manifest_uses_wikipedia_page_id_and_keeps_cmu_text_out(tmp_path):
    metadata = tmp_path / "metadata.tsv"
    plots = tmp_path / "plots.txt"
    output = tmp_path / "candidates.json"
    metadata.write_text(
        '10\t/fb/1\tExample Film\t2008-01-02\t\t120\t{"en":"English Language"}\t{}\t{}\n'
        '11\t/fb/2\tBad Date\t1010-12-02\t\t\t{"x":"English Language"}\t{}\t{}\n',
        encoding="utf-8",
    )
    plots.write_text("10\tTHIS PRIVATE TEST SUMMARY MUST NOT BE COPIED\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts/prepare_cmu_movie_candidates.py"),
         "--metadata", str(metadata), "--plots", str(plots), "--output", str(output)],
        cwd=PROJECT_ROOT, check=True, capture_output=True, text=True,
    )
    report = json.loads(result.stdout)
    manifest = json.loads(output.read_text(encoding="utf-8"))

    assert report["counts"]["candidate_rows"] == 2
    assert report["counts"]["release_year_valid"] == 1
    assert report["counts"]["release_year_missing_or_anomalous"] == 1
    assert manifest["candidate_only"] is True
    assert manifest["candidates"][0]["wikipedia_page_id"] == 10
    assert manifest["candidates"][0]["release_year_candidate"] == 2008
    assert manifest["candidates"][0]["historical_plot_summary_available"] is True
    assert manifest["candidates"][1]["release_year_candidate"] is None
    assert "THIS PRIVATE TEST SUMMARY" not in output.read_text(encoding="utf-8")
    assert "/fb/1" not in output.read_text(encoding="utf-8")


def test_manifest_quarantines_bad_rows_and_marks_unknown_language(tmp_path):
    metadata = tmp_path / "metadata.tsv"
    plots = tmp_path / "plots.txt"
    output = tmp_path / "candidates.json"
    metadata.write_text("oops\tbad\n12\t/fb/3\tUnknown Language\t2001\t\t\t{}\t{}\t{}\n", encoding="utf-8")
    plots.write_text("bad row\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts/prepare_cmu_movie_candidates.py"),
         "--metadata", str(metadata), "--plots", str(plots), "--output", str(output)],
        cwd=PROJECT_ROOT, check=True, capture_output=True, text=True,
    )
    report = json.loads(result.stdout)
    candidate = json.loads(output.read_text(encoding="utf-8"))["candidates"][0]

    assert report["counts"]["quarantined_metadata_rows"] == 1
    assert report["counts"]["malformed_plot_rows"] == 1
    assert candidate["english_language_candidate"] == "unknown"
    assert candidate["historical_plot_summary_available"] is False
