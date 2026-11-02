"""Explicit manual download of two pinned public benchmarks; never product ingestion.

No model, database or third-party code is loaded. Run with the project's Conda Python.
Raw text and benchmark labels remain under ignored data/evaluation/external/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "data/evaluation/external"
AGENT = "CineGraphResearch/1.0 (manual public dataset acquisition)"
RELEASES = {
    "narrative-similarity": (
        "narrative-similarity-task/narrative-similarity-dataset",
        "ef7375dd08172c804ffa6706aa94d003e59f5015",
    ),
    "mf2": (
        "deep-spin/MF2-bench-how-well-vlms-understand-movies",
        "e00ff56479c88fcc9947d4975c8deba93e42e922",
    ),
}


def selected(name: str, path: str) -> bool:
    if path == "README.md":
        return True
    if name == "narrative-similarity":
        return path.endswith(".jsonl") and path.split("/")[0] in {"dev", "sample", "test"}
    return path == "data/MF2_test.csv" or (
        path.startswith(("data/transcripts/", "data/synopsis/"))
        and path.endswith((".srt", ".synopsis"))
    )


def fetch(url: str, limit: int) -> bytes:
    # Deliberately sequential. HTTP errors including 429/403 stop the job; no evasion.
    time.sleep(1)
    with urlopen(Request(url, headers={"User-Agent": AGENT}), timeout=40) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Download exceeds the explicit byte budget.")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="Explicitly enable network downloads")
    args = parser.parse_args()
    if not args.download:
        parser.error("This is a manual network action; pass --download.")
    if not DEST.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError("Evaluation storage must stay inside this project.")
    robots_url = "https://raw.githubusercontent.com/robots.txt"
    try:
        robots = fetch(robots_url, 1_000_000).decode()
        robots_status = 200
    except HTTPError as exc:
        if exc.code != 404:
            raise
        robots, robots_status = "", 404
    policy = RobotFileParser(robots_url)
    policy.parse(robots.splitlines())
    for name, (repo, revision) in RELEASES.items():
        tree = json.loads(fetch(f"https://api.github.com/repos/{repo}/git/trees/{revision}?recursive=1", 2_000_000))
        if tree.get("truncated") or tree.get("sha") != revision:
            raise ValueError("Incomplete or mismatched pinned release tree.")
        files = [item for item in tree["tree"] if item["type"] == "blob" and selected(name, item["path"])]
        if not files or len(files) > 128 or sum(item["size"] for item in files) > 25_000_000:
            raise ValueError("Missing dataset or release exceeds 25 MB budget.")
        directory = DEST / name / revision
        records = []
        for item in files:
            path = item["path"]
            target = directory / path
            if not target.resolve().is_relative_to(DEST.resolve()):
                raise ValueError("Unsafe release path.")
            url = f"https://raw.githubusercontent.com/{repo}/{revision}/{path}"
            if robots_status == 200 and not policy.can_fetch(AGENT, url):
                raise ValueError(f"robots.txt disallows {url}")
            payload = target.read_bytes() if target.exists() else fetch(url, item["size"])
            git_blob = hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()
            if len(payload) != item["size"] or git_blob != item["sha"]:
                raise ValueError(f"Pinned blob verification failed: {path}")
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
            records.append({"path": path, "bytes": len(payload), "url": url,
                            "sha256": hashlib.sha256(payload).hexdigest(), "git_blob_sha1": git_blob})
            print(f"{name}: verified {path}", flush=True)
        manifest = {"repository": repo, "revision": revision,
                    "acquired_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "purpose": "evaluation-only; not training or product evidence",
                    "robots_url": robots_url, "robots_http_status": robots_status, "files": records}
        manifest_path = directory / "acquisition-manifest.json"
        if not manifest_path.resolve().is_relative_to(DEST.resolve()):
            raise ValueError("Manifest must stay inside local evaluation storage.")
        manifest_path.write_text(json.dumps(manifest, indent=2))
        print(f"{name}: {len(records)} files, {sum(r['bytes'] for r in records)} bytes", flush=True)


if __name__ == "__main__":
    main()
