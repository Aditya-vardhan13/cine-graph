"""Pure adapters for external narrative research data, not operational facts."""
from __future__ import annotations

import hashlib
import re


def text_id(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def category_set(raw: str) -> list[str]:
    return sorted({part.strip() for part in raw.split(",") if part.strip()})


def claim_pair_status(row: dict) -> str:
    first, second = row["true_claim"].strip(), row["false_claim"].strip()
    if not first or not second:
        return "empty_claim"
    if first == second:
        return "identical_claims"
    return "eligible_for_review"


def claim_arms(pair_id: str, row: dict) -> list[tuple[str, str, bool]]:
    """Counterbalance true/false position without changing the released labels."""
    fields = [("true_claim", True), ("false_claim", False)]
    if int(text_id(pair_id)[0], 16) % 2:
        fields.reverse()
    return [(arm, row[field], truth) for arm, (field, truth) in zip(("a", "b"), fields)]


def srt_text(raw: str) -> tuple[str, list[dict]]:
    """Remove SRT counters/times, retaining exact dialogue-to-raw offset maps.

    No invented speakers, HTML stripping, text correction or scene inference.
    Untimed text blocks remain explicitly untimed; malformed time headers fail.
    """
    pattern = re.compile(
        r"(?:\ufeff)?(?P<number>-?\d+)\r?\n"
        r"(?P<start>\d{2}:\d{2}:\d{2}[,.]\d{1,3})[ \t]+-->[ \t]+"
        r"(?P<end>\d{2}:\d{2}:\d{2}[,.]\d{1,3})[^\r\n]*\r?\n"
        r"(?P<text>.*)", re.DOTALL,
    )
    pieces, maps, position, cursor, timed = [], [], 0, 0, 0
    previous_start = -1
    def milliseconds(value):
        h, m, sec, fraction = re.split(r"[:,.]", value)
        h, m, sec, ms = int(h), int(m), int(sec), int(fraction.ljust(3, "0"))
        if m >= 60 or sec >= 60:
            raise ValueError("Invalid subtitle timestamp.")
        return ((h * 60 + m) * 60 + sec) * 1000 + ms
    boundaries = [m.start() for m in re.finditer(r"\r?\n[ \t]*\r?\n", raw)] + [len(raw)]
    for boundary in boundaries:
        start_offset = cursor
        block = raw[cursor:boundary]
        cursor = boundary
        while start_offset < boundary and raw[start_offset] in "\r\n":
            start_offset += 1
        block = raw[start_offset:boundary]
        if not block.strip():
            continue
        match = pattern.fullmatch(block)
        start, end, number = None, None, None
        if match:
            start, end = milliseconds(match["start"]), milliseconds(match["end"])
            if start > end or start < previous_start:
                raise ValueError("Nonmonotonic or reversed subtitle time.")
            previous_start, number = start, int(match["number"])
            text, raw_start, raw_end = match["text"], start_offset + match.start("text"), start_offset + match.end("text")
            timed += 1
        else:
            if "-->" in block:
                raise ValueError("Malformed subtitle time header.")
            text, raw_start, raw_end = block, start_offset, boundary
        if not text.strip():
            raise ValueError("Empty subtitle cue.")
        if pieces:
            position += 1
        maps.append({"cue_number": number, "start_ms": start, "end_ms": end,
                     "timestamp_status": "source-cue" if match else "untimed-source-block",
                     "raw_start": raw_start, "raw_end": raw_end,
                     "content_start": position, "content_end": position + len(text)})
        pieces.append(text)
        position += len(text)
    if not timed:
        raise ValueError("Unparsed or empty subtitle document.")
    return "\n".join(pieces), maps


def passage_windows(content: str, words: int = 160, overlap: int = 32) -> list[dict]:
    if not words > overlap >= 0:
        raise ValueError("Invalid chunk budget.")
    tokens = list(re.finditer(r"\S+", content))
    spans = []
    for offset in range(0, len(tokens), words - overlap):
        stop = min(offset + words, len(tokens))
        start, end = tokens[offset].start(), tokens[stop - 1].end()
        spans.append({"start": start, "end": end, "content": content[start:end]})
        if stop == len(tokens):
            break
    return spans


def narrative_case(row: dict, *, split: str, case_id: str) -> tuple[dict, dict | None]:
    """Project model inputs explicitly; never pass label-bearing source dicts."""
    prompt = {"case_id": case_id, "dataset": "narrative-similarity", "official_split": split,
              "task": "relative_story_similarity", "stories": {
                  role: text_id(row[key]) for role, key in
                  (("anchor", "anchor_text"), ("a", "text_a"), ("b", "text_b"))}}
    gold = None
    if "text_a_is_closer" in row:
        if type(row["text_a_is_closer"]) is not bool:
            raise ValueError("Narrative label must be boolean.")
        gold = {"case_id": case_id, "a_is_closer": row["text_a_is_closer"],
                "dimensions": {key: row.get(key) for key in
                               ("abstract_theme", "course_of_actions", "outcomes")},
                "human_labels": row.get("human_labels"), "canary_string": row.get("canary_string")}
    return prompt, gold
