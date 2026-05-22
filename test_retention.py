from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from harvester.retention import DEFAULT_POLICY, apply_retention


def _write_file(path: Path, content: bytes = b"data", age_days: int = 0) -> Path:
    """Write a file and optionally back-date its mtime."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    if age_days:
        old = time.time() - age_days * 86400
        os.utime(path, (old, old))
    return path


class RetentionDryRunTests(unittest.TestCase):
    def test_dry_run_makes_no_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Write a very old PDF
            old_pdf = _write_file(root / "Bulletins" / "current" / "old.pdf", age_days=70)
            # Apply with dry_run
            report = apply_retention(root, dry_run=True)
            # File must still exist
            self.assertTrue(old_pdf.exists(), "dry_run must not delete files")
            # Report should have recorded it
            self.assertIn("before_bytes", report)
            self.assertIn("after_bytes", report)


class RetentionOldFilesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        self.root = Path(self._tmp)
        # Write a minimal retention_policy with short windows for testing
        policy = {
            "keep_weeks_individual": 1,
            "keep_weeks_mega_pdf": 1,
            "keep_months_archive": 1,
            "hard_size_cap_gb": 100.0,
        }
        (self.root / "parishes").mkdir(parents=True, exist_ok=True)
        (self.root / "parishes" / "retention_policy.json").write_text(
            json.dumps(policy), encoding="utf-8"
        )

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_old_individual_pdfs_zipped_and_removed(self) -> None:
        old_pdf = _write_file(
            self.root / "Bulletins" / "current" / "old_parish.pdf",
            content=b"%PDF-1.4 old",
            age_days=14,  # > 1 week
        )
        report = apply_retention(self.root, dry_run=False)

        # Original should be gone
        self.assertFalse(old_pdf.exists(), "Old PDF should be removed after zipping")
        # At least one zip should exist
        archive_dir = self.root / "Bulletins" / "archive"
        zips = list(archive_dir.glob("*.zip"))
        self.assertGreater(len(zips), 0, "Expected at least one archive zip")
        # Report should list the file
        self.assertGreater(len(report["zipped_files"]), 0)

    def test_recent_pdfs_not_touched(self) -> None:
        new_pdf = _write_file(
            self.root / "Bulletins" / "current" / "new.pdf",
            content=b"%PDF-1.4 new",
            age_days=0,
        )
        apply_retention(self.root, dry_run=False)
        self.assertTrue(new_pdf.exists(), "Recent PDF should NOT be removed")

    def test_report_keys_present(self) -> None:
        report = apply_retention(self.root, dry_run=False)
        for key in ("before_bytes", "after_bytes", "zipped_files", "deleted_files", "warnings"):
            self.assertIn(key, report, f"Missing key: {key}")

    def test_old_archives_deleted(self) -> None:
        archive_dir = self.root / "Bulletins" / "archive"
        # Write an old zip (> 1 month ago)
        old_zip = _write_file(
            archive_dir / "2024-01-individual-pdfs.zip",
            content=b"PK\x03\x04",  # ZIP magic bytes
            age_days=400,  # > 1 month
        )
        apply_retention(self.root, dry_run=False)
        self.assertFalse(old_zip.exists(), "Very old archive zip should be deleted")


class RetentionHardCapTests(unittest.TestCase):
    def test_hard_cap_triggers_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy = {
                "keep_weeks_individual": 1,
                "keep_weeks_mega_pdf": 1,
                "keep_months_archive": 1,
                "hard_size_cap_gb": 0.000001,  # 1 KB cap — will always trigger
            }
            (root / "parishes").mkdir(parents=True, exist_ok=True)
            (root / "parishes" / "retention_policy.json").write_text(
                json.dumps(policy), encoding="utf-8"
            )
            # Write enough data to exceed cap
            _write_file(root / "Bulletins" / "current" / "big.pdf", content=b"x" * 2048)

            report = apply_retention(root, dry_run=False)
            self.assertTrue(
                any("hard cap" in w.lower() or "exceeds" in w.lower() for w in report["warnings"]),
                f"Expected a hard cap warning, got: {report['warnings']}",
            )

    def test_default_policy_loaded_when_no_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = apply_retention(root, dry_run=True)
            self.assertIn("before_bytes", report)


class RetentionPolicyTests(unittest.TestCase):
    def test_custom_policy_respected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy = {
                "keep_weeks_individual": 52,  # very long — nothing should be pruned
                "keep_weeks_mega_pdf": 52,
                "keep_months_archive": 24,
                "hard_size_cap_gb": 100.0,
            }
            (root / "parishes").mkdir(parents=True, exist_ok=True)
            (root / "parishes" / "retention_policy.json").write_text(
                json.dumps(policy), encoding="utf-8"
            )
            # Write a 3-week-old PDF — should be kept under 52-week policy
            old_pdf = _write_file(
                root / "Bulletins" / "current" / "old.pdf",
                content=b"%PDF-1.4",
                age_days=21,
            )
            apply_retention(root, dry_run=False)
            self.assertTrue(old_pdf.exists(), "File within retention window should NOT be pruned")


if __name__ == "__main__":
    unittest.main()
