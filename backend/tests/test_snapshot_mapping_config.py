import pytest
import hashlib
import json
import os
import subprocess
import sys
from pydantic import ValidationError

from app.core.config import Settings


def test_snapshot_maps_are_explicit_and_default_to_native_paths():
    assert Settings(_env_file=None).snapshot_root_mappings == []
    settings = Settings(_env_file=None, snapshot_root_mappings=[
        ("/host/project/data", "/app/data"),
        ("/var/lib/cinegraph/raw-snapshots", "/var/lib/cinegraph/raw-snapshots"),
    ])
    assert len(settings.snapshot_root_mappings) == 2


@pytest.mark.parametrize("maps", [
    [("relative", "/app/data")], [("/host/data", "/")],
    [("/", "/app/data")], [("/host/data", "../data")],
    [("/host/data", "/app/data"), ("/host/data", "/app/other")],
])
def test_invalid_snapshot_maps_fail_at_configuration(maps):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, snapshot_root_mappings=maps)


def test_application_verifier_uses_real_configured_mapping(tmp_path):
    mounted = tmp_path / "mount"
    mounted.mkdir()
    payload = b"retained source bytes"
    (mounted / "source.json").write_bytes(payload)
    env = {**os.environ, "SNAPSHOT_ROOT_MAPPINGS": json.dumps([
        ["/host/source-data", str(mounted)],
    ])}
    script = (
        "from app.services.snapshot_integrity import verify_snapshot_file; "
        f"print(verify_snapshot_file('file:///host/source-data/source.json', "
        f"{hashlib.sha256(payload).hexdigest()!r}, {len(payload)})); "
        "print(verify_snapshot_file('file:///unmapped/source.json', '0'*64, None))"
    )
    result = subprocess.run([sys.executable, "-c", script], env=env,
                            text=True, capture_output=True, check=True)
    assert result.stdout.splitlines() == ["verified", "unmapped"]


def test_mapping_rejects_symlink_escape(tmp_path):
    from pathlib import Path
    from app.services.snapshot_integrity import verify_snapshot_file
    mounted = tmp_path / "mount"
    mounted.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"private")
    (mounted / "escape.json").symlink_to(outside)
    assert verify_snapshot_file(
        "file:///host/data/escape.json", hashlib.sha256(b"private").hexdigest(), 7,
        root_mappings=((Path("/host/data"), mounted),),
    ) == "unmapped"
