"""Pure selection-policy checks. No download, source crawling or database access."""
import importlib.util
from pathlib import Path


spec = importlib.util.spec_from_file_location(
    "narrative_acquisition",
    Path(__file__).resolve().parents[2] / "scripts/acquire_narrative_benchmarks.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_narrative_release_keeps_original_splits_and_licence_readme():
    assert module.selected("narrative-similarity", "README.md")
    assert module.selected("narrative-similarity", "dev/dev_track_a.jsonl")
    assert module.selected("narrative-similarity", "test/labels/test_track_a_labels.jsonl")
    assert not module.selected("narrative-similarity", "training/generated.jsonl")
    assert not module.selected("narrative-similarity", "dev/script.py")


def test_mf2_acquisition_does_not_download_video_or_duplicate_cropped_context():
    assert module.selected("mf2", "data/MF2_test.csv")
    assert module.selected("mf2", "data/transcripts/1.srt")
    assert module.selected("mf2", "data/synopsis/1.synopsis")
    assert not module.selected("mf2", "data/1.mp4")
    assert not module.selected("mf2", "models/remote_code.py")
    assert not module.selected("mf2", "data/cropped_experiment_data/transcripts_full/13/13_claim_0.srt")
