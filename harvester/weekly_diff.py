from __future__ import annotations

import difflib
import re

MAX_LINES_PER_SIDE = 30
MIN_LINE_LENGTH = 20


def _normalise_lines(text: str) -> list[str]:
    normalized: list[str] = []
    for raw in (text or "").splitlines():
        line = re.sub(r"\s+", " ", raw.strip().lower()).strip()
        if not line:
            continue
        if len(line) < MIN_LINE_LENGTH:
            continue
        normalized.append(line)
    return normalized


def diff_bulletins(this_week_text: str, last_week_text: str) -> dict:
    this_lines = _normalise_lines(this_week_text)
    last_lines = _normalise_lines(last_week_text)

    unified = list(difflib.unified_diff(last_lines, this_lines, fromfile="last_week", tofile="this_week", lineterm=""))

    added_lines: list[str] = []
    removed_lines: list[str] = []
    for line in unified:
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            continue
        if line.startswith("+"):
            added_lines.append(line[1:])
        elif line.startswith("-"):
            removed_lines.append(line[1:])

    kept_count = sum(
        block.size
        for block in difflib.SequenceMatcher(a=last_lines, b=this_lines).get_matching_blocks()
        if block.size > 0
    )

    added_truncated = len(added_lines) > MAX_LINES_PER_SIDE
    removed_truncated = len(removed_lines) > MAX_LINES_PER_SIDE
    if added_truncated:
        added_lines = sorted(added_lines, key=len, reverse=True)[:MAX_LINES_PER_SIDE]
    if removed_truncated:
        removed_lines = sorted(removed_lines, key=len, reverse=True)[:MAX_LINES_PER_SIDE]

    result: dict[str, object] = {
        "added_lines": added_lines,
        "removed_lines": removed_lines,
        "kept_count": kept_count,
    }
    if added_truncated or removed_truncated:
        result["note"] = "truncated_to_30_lines_per_side"
    return result
