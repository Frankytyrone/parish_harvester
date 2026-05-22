from __future__ import annotations

"""Retention policy — zip old bulletins, purge very old archives.

Prevents the GitHub repository from hitting its 5 GB hard cap.
At 1000+ parishes × ~500 KB PDFs × 52 weeks ≈ 26 GB/year without this.

Configurable via ``parishes/retention_policy.json`` (see defaults below).

Usage::

    from pathlib import Path
    from harvester.retention import apply_retention

    report = apply_retention(Path("."))          # live run
    report = apply_retention(Path("."), dry_run=True)  # preview only
"""

import json
import os
import shutil
import tempfile
import zipfile
from calendar import monthrange
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Default policy — can be overridden by parishes/retention_policy.json
# ---------------------------------------------------------------------------
DEFAULT_POLICY: dict = {
    "keep_weeks_individual": 8,
    "keep_weeks_mega_pdf": 12,
    "keep_months_archive": 24,
    "hard_size_cap_gb": 4.0,
}

GB = 1024 ** 3


def _load_policy(repo_root: Path) -> dict:
    policy_path = repo_root / "parishes" / "retention_policy.json"
    if not policy_path.exists():
        return dict(DEFAULT_POLICY)
    try:
        loaded = json.loads(policy_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            return dict(DEFAULT_POLICY)
        merged = dict(DEFAULT_POLICY)
        merged.update(loaded)
        return merged
    except Exception:  # noqa: BLE001
        return dict(DEFAULT_POLICY)


def _repo_size_bytes(repo_root: Path) -> int:
    """Sum of all non-hidden tracked files on disk (fast approximation)."""
    total = 0
    for p in repo_root.rglob("*"):
        if p.is_file() and ".git" not in p.parts:
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def _week_cutoff(weeks: int) -> datetime:
    """UTC datetime *weeks* weeks before now."""
    from datetime import timedelta

    return datetime.now(timezone.utc) - timedelta(weeks=weeks)


def _month_cutoff(months: int) -> datetime:
    """UTC datetime *months* months before now."""
    now = datetime.now(timezone.utc)
    year = now.year - (months // 12)
    month = now.month - (months % 12)
    if month <= 0:
        month += 12
        year -= 1
    day = min(now.day, monthrange(year, month)[1])
    return now.replace(year=year, month=month, day=day)


def _zip_label(year: int, month: int, kind: str) -> str:
    return f"{year:04d}-{month:02d}-{kind}.zip"


def _build_zip_atomic(
    archive_dir: Path, label: str, files: list[Path], dry_run: bool
) -> Path | None:
    """Build zip from *files*, place in *archive_dir/label*.

    Returns the zip path if successful; None on failure.
    Verifies the zip before replacing any original files.
    """
    out_path = archive_dir / label
    if dry_run:
        return out_path  # pretend success
    archive_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(suffix=".tmp.zip", dir=archive_dir)
    try:
        with os.fdopen(fd, "wb") as _fh:
            pass  # close so zipfile can open it
        with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                zf.write(f, f.name)
        # Verify
        with zipfile.ZipFile(tmp_path, "r") as zf:
            bad = zf.testzip()
            if bad:
                raise RuntimeError(f"Zip verification failed on {bad}")
        os.replace(tmp_path, out_path)
        return out_path
    except Exception as exc:  # noqa: BLE001
        print(f"[retention] Failed to build zip {label}: {exc}")
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        return None


def _collect_old_files(directory: Path, cutoff: datetime, suffixes: set[str]) -> list[Path]:
    """Collect files in *directory* older than *cutoff* with matching suffix."""
    results: list[Path] = []
    if not directory.is_dir():
        return results
    for f in directory.iterdir():
        if not f.is_file():
            continue
        if f.suffix.lower() not in suffixes:
            continue
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
        except OSError:
            continue
        if mtime < cutoff:
            results.append(f)
    return results


def _group_by_year_month(files: list[Path]) -> dict[tuple[int, int], list[Path]]:
    groups: dict[tuple[int, int], list[Path]] = {}
    for f in files:
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
        except OSError:
            continue
        key = (mtime.year, mtime.month)
        groups.setdefault(key, []).append(f)
    return groups


def apply_retention(root: Path, dry_run: bool = False) -> dict:
    """Apply retention rules to the repository at *root*.

    Parameters
    ----------
    root:
        Repository root directory.
    dry_run:
        If True, compute what *would* be done but make no changes to disk.

    Returns
    -------
    dict
        Report with keys: ``before_bytes``, ``after_bytes``,
        ``zipped_files``, ``deleted_files``, ``warnings``.
    """
    policy = _load_policy(root)
    keep_weeks_individual = int(policy.get("keep_weeks_individual", DEFAULT_POLICY["keep_weeks_individual"]))
    keep_weeks_mega_pdf = int(policy.get("keep_weeks_mega_pdf", DEFAULT_POLICY["keep_weeks_mega_pdf"]))
    keep_months_archive = int(policy.get("keep_months_archive", DEFAULT_POLICY["keep_months_archive"]))
    hard_cap_bytes = float(policy.get("hard_size_cap_gb", DEFAULT_POLICY["hard_size_cap_gb"])) * GB

    archive_dir = root / "Bulletins" / "archive"

    before_bytes = _repo_size_bytes(root)
    zipped_files: list[str] = []
    deleted_files: list[str] = []
    warnings: list[str] = []

    # -----------------------------------------------------------------------
    # Step 1 — Compress old individual parish PDFs
    # -----------------------------------------------------------------------
    individual_cutoff = _week_cutoff(keep_weeks_individual)
    individual_dirs: list[Path] = []
    bulletins_current = root / "Bulletins" / "current"
    if bulletins_current.is_dir():
        individual_dirs.append(bulletins_current)

    for ind_dir in individual_dirs:
        old_pdfs = _collect_old_files(ind_dir, individual_cutoff, {".pdf"})
        if not old_pdfs:
            continue
        for (year, month), group in _group_by_year_month(old_pdfs).items():
            label = _zip_label(year, month, "individual-pdfs")
            if (archive_dir / label).exists():
                # Already archived; just delete originals
                if not dry_run:
                    for f in group:
                        try:
                            f.unlink()
                            deleted_files.append(str(f.relative_to(root)))
                        except OSError as exc:
                            warnings.append(f"Could not delete {f}: {exc}")
                continue
            zip_path = _build_zip_atomic(archive_dir, label, group, dry_run)
            if zip_path is not None:
                for f in group:
                    zipped_files.append(str(f.relative_to(root)))
                    if not dry_run:
                        try:
                            f.unlink()
                            deleted_files.append(str(f.relative_to(root)))
                        except OSError as exc:
                            warnings.append(f"Could not delete {f} after zipping: {exc}")

    # -----------------------------------------------------------------------
    # Step 2 — Compress old mega PDFs
    # -----------------------------------------------------------------------
    mega_cutoff = _week_cutoff(keep_weeks_mega_pdf)
    mega_dirs = [root / "mega_pdf", root / "docs" / "mega_pdf"]
    for mega_dir in mega_dirs:
        old_megas = _collect_old_files(mega_dir, mega_cutoff, {".pdf"})
        if not old_megas:
            continue
        for (year, month), group in _group_by_year_month(old_megas).items():
            label = _zip_label(year, month, "mega-pdfs")
            if (archive_dir / label).exists():
                if not dry_run:
                    for f in group:
                        try:
                            f.unlink()
                            deleted_files.append(str(f.relative_to(root)))
                        except OSError as exc:
                            warnings.append(f"Could not delete {f}: {exc}")
                continue
            zip_path = _build_zip_atomic(archive_dir, label, group, dry_run)
            if zip_path is not None:
                for f in group:
                    zipped_files.append(str(f.relative_to(root)))
                    if not dry_run:
                        try:
                            f.unlink()
                            deleted_files.append(str(f.relative_to(root)))
                        except OSError as exc:
                            warnings.append(f"Could not delete {f} after zipping: {exc}")

    # -----------------------------------------------------------------------
    # Step 3 — Delete very old archive zips
    # -----------------------------------------------------------------------
    archive_cutoff = _month_cutoff(keep_months_archive)
    if archive_dir.is_dir():
        for f in archive_dir.iterdir():
            if not f.is_file() or f.suffix.lower() != ".zip":
                continue
            try:
                mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            except OSError:
                continue
            if mtime < archive_cutoff:
                if not dry_run:
                    try:
                        f.unlink()
                        deleted_files.append(str(f.relative_to(root)))
                    except OSError as exc:
                        warnings.append(f"Could not delete old archive {f}: {exc}")
                else:
                    deleted_files.append(str(f.relative_to(root)))  # dry-run: record intent

    # -----------------------------------------------------------------------
    # Step 4 — Hard size cap check
    # -----------------------------------------------------------------------
    after_bytes = _repo_size_bytes(root)
    if after_bytes > hard_cap_bytes:
        pct = after_bytes / hard_cap_bytes * 100
        msg = (
            f"🚨 Repository size {after_bytes / GB:.2f} GB exceeds hard cap "
            f"{hard_cap_bytes / GB:.2f} GB ({pct:.0f}%). "
            "Emergency pruning required — oldest archives removed first."
        )
        warnings.append(msg)
        print(f"[retention] {msg}")
        # Emergency prune: delete oldest archive zips until under cap
        if not dry_run and archive_dir.is_dir():
            zips = sorted(
                [f for f in archive_dir.iterdir() if f.is_file() and f.suffix.lower() == ".zip"],
                key=lambda f: f.stat().st_mtime,
            )
            for f in zips:
                if _repo_size_bytes(root) <= hard_cap_bytes:
                    break
                try:
                    f.unlink()
                    deleted_files.append(str(f.relative_to(root)))
                    print(f"[retention] Emergency pruned: {f.name}")
                except OSError as exc:
                    warnings.append(f"Emergency prune failed for {f}: {exc}")

    return {
        "before_bytes": before_bytes,
        "after_bytes": after_bytes,
        "zipped_files": zipped_files,
        "deleted_files": deleted_files,
        "warnings": warnings,
    }
