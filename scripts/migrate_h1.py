#!/usr/bin/env python3
"""migrate_h1.py — one-time migration for Bundle H1.

Moves flat JSON files in:
  Bulletins/summaries/<parish_key>.json  → Bulletins/summaries/unknown/<parish_key>.json
  Bulletins/diffs/<parish_key>.json      → Bulletins/diffs/unknown/<parish_key>.json
  recipes/learned/<parish_key>.json      → recipes/learned/unknown/<parish_key>.json

Why "unknown"?  These old flat files predate per-diocese paths, so the
diocese cannot be recovered from the filename alone.  After migration, edit
the "diocese" field in each ``recipes/learned/unknown/<parish_key>.json`` to
the correct diocese and move the file manually to the right subfolder.

Run once, locally:
    python scripts/migrate_h1.py [--dry-run]

Files that already live in a subfolder (i.e. not directly under the base dir)
are skipped so the script is safe to re-run.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SUMMARIES_DIR = REPO_ROOT / "Bulletins" / "summaries"
DIFFS_DIR = REPO_ROOT / "Bulletins" / "diffs"
LEARNED_DIR = REPO_ROOT / "recipes" / "learned"


def _migrate_dir(base_dir: Path, target_subdir: str, dry_run: bool) -> int:
    moved = 0
    if not base_dir.exists():
        print(f"  ⚠ {base_dir} does not exist — skipping.")
        return 0
    dest_dir = base_dir / target_subdir
    for src in sorted(base_dir.glob("*.json")):
        if src.name.startswith("_"):
            continue  # skip _index.json etc.
        dest = dest_dir / src.name
        print(f"  {'[DRY RUN] ' if dry_run else ''}mv {src.relative_to(REPO_ROOT)}  →  {dest.relative_to(REPO_ROOT)}")
        if not dry_run:
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
        moved += 1
    return moved


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate H1 flat JSON files to per-diocese subfolders.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen without moving files.")
    args = parser.parse_args()

    dry_run: bool = args.dry_run
    if dry_run:
        print("DRY RUN — no files will be moved.\n")

    total = 0
    for label, base_dir in [
        ("Bulletins/summaries", SUMMARIES_DIR),
        ("Bulletins/diffs", DIFFS_DIR),
        ("recipes/learned", LEARNED_DIR),
    ]:
        print(f"\n{label}:")
        total += _migrate_dir(base_dir, "unknown", dry_run)

    print(f"\n{'Would move' if dry_run else 'Moved'} {total} file(s).")
    if dry_run:
        print("Re-run without --dry-run to apply.")


if __name__ == "__main__":
    main()
