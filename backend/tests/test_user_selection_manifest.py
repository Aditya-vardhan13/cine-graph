import csv
import json

from app.services.user_selection_manifest import build_manifest, read_title_year_rows, write_manifest


def test_private_selection_manifest_reads_only_title_and_year(tmp_path) -> None:
    source = tmp_path / "titles.csv"
    with source.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Series_Title", "Released_Year", "IMDB_Rating", "Overview"])
        writer.writeheader()
        writer.writerow({"Series_Title": "Fixture One", "Released_Year": "2020", "IMDB_Rating": "9.9", "Overview": "Excluded"})
        writer.writerow({"Series_Title": "Fixture Two", "Released_Year": "2019", "IMDB_Rating": "9.8", "Overview": "Excluded"})

    manifest = build_manifest(source)
    output, _ = write_manifest(manifest, tmp_path / "manifest.json")

    assert read_title_year_rows(source) == [
        {"position": 1, "title": "Fixture One", "release_year": 2020},
        {"position": 2, "title": "Fixture Two", "release_year": 2019},
    ]
    saved = json.loads(output.read_text())
    assert saved["input"]["fields_used"] == ["Series_Title", "Released_Year"]
    assert "IMDB_Rating" not in output.read_text()
