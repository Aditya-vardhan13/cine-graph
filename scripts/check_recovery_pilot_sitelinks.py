"""Capture a bounded Wikidata identity cross-check; never approve or import."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx

from app.services.corpus_build_manifest import canonical_digest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--contact", required=True, help="Contact identifier for Wikimedia User-Agent")
    args = parser.parse_args()
    root = Path.cwd().resolve() / "data"
    if (not args.corpus.resolve().is_relative_to(root / "evaluation")
            or not args.output.resolve().is_relative_to(root / "reports") or args.output.exists()):
        raise ValueError("new_local_report_required")
    corpus = json.loads(args.corpus.read_text())
    if canonical_digest({k: v for k, v in corpus.items() if k != "fingerprint"}) != corpus["fingerprint"]:
        raise ValueError("corpus_fingerprint_mismatch")
    sources = {}
    for doc in corpus["documents"]:
        qid, url = doc["film_qid"], doc["source_url"]
        if qid in sources and sources[qid] != url:
            raise ValueError("ambiguous_film_source")
        sources[qid] = url
    if len(sources) != 10:
        raise ValueError("unexpected_pilot_size")
    response = httpx.get("https://www.wikidata.org/w/api.php", timeout=30,
        headers={"User-Agent": f"CineGraphResearch/0.1 ({args.contact})"},
        params={"action": "wbgetentities", "ids": "|".join(sorted(sources)), "props": "sitelinks",
                "sitefilter": "enwiki", "format": "json", "maxlag": 5})
    response.raise_for_status()
    payload = response.json()
    if "error" in payload:
        raise RuntimeError("Wikidata returned an API error; no decisions recorded")
    records = []
    for qid, url in sorted(sources.items()):
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc != "en.wikipedia.org" or not parsed.path.startswith("/wiki/"):
            raise ValueError("unexpected_wikipedia_url")
        expected_title = unquote(parsed.path.removeprefix("/wiki/")).replace("_", " ")
        actual_title = payload.get("entities", {}).get(qid, {}).get("sitelinks", {}).get("enwiki", {}).get("title")
        records.append({"qid": qid, "source_url": url, "wikidata_enwiki_title": actual_title,
                        "matches_source_url": expected_title == actual_title})
    result = {"schema": "cinegraph.pilot-wikidata-sitelink-check/v1", "corpus_fingerprint": corpus["fingerprint"],
        "request_url": str(response.request.url), "retrieved_at": response.headers.get("date"),
        "response_sha256": hashlib.sha256(response.content).hexdigest(), "raw_response": response.text,
        "rows": records, "identity_approved": False,
        "caution": "Sitelink agreement and source-lead review are identity evidence, not an independent identity approval."}
    result["report_sha256"] = canonical_digest(result)
    with args.output.open("x") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"films": len(records), "sitelink_matches": sum(x["matches_source_url"] for x in records),
                      "report_sha256": result["report_sha256"]}))


if __name__ == "__main__":
    main()
