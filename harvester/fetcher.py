"""
fetcher.py — Evidence-driven bulletin downloader for the Parish Bulletin Harvester.

Reads parishes/{diocese}_bulletin_urls.txt, calculates this week's URL using
date math, and downloads each bulletin directly.  No crawling, no guessing.
"""
from __future__ import annotations

import asyncio
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from playwright.async_api import (
    Browser,
    async_playwright,
    TimeoutError as PlaywrightTimeout,
)
try:
    from playwright._impl._errors import TargetClosedError as _TargetClosedError
except Exception:
    _TargetClosedError = Exception  # type: ignore[assignment,misc]

from .config import (
    CONCURRENCY,
    MIN_PDF_BYTES,
    PAGE_LOAD_TIMEOUT_MS,
    PARISHES_DIR,
    TOTAL_TIMEOUT_S,
)
from .utils import (
    extract_newsletter_number,
    is_valid_pdf,
    rewrite_clonleigh_url,
    rewrite_date_url,
    rewrite_greenlough_url,
    rewrite_newsletter_number_url,
    safe_filename,
)

# Seconds to wait after all tasks finish before closing the browser
_PLAYWRIGHT_SHUTDOWN_DELAY_S: float = 0.5
# Number of attempts (1 original + 1 retry)
_MAX_ATTEMPTS: int = 2
# Seconds to wait between retry attempts
_RETRY_DELAY_S: float = 3.0


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ParishEntry:
    """One parish extracted from the evidence file."""
    key: str            # e.g. "ardmoreparish"
    display_name: str   # e.g. "Ardmore Parish"
    pattern: str        # "A"-"H", "greenlough", "clonleigh", "html_link", "F"
    content_type: str   # "pdf" | "docx" | "image" | "html_link"
    example_url: str    # Most recent confirmed URL (used for date math)
    all_urls: list[str] = field(default_factory=list)


@dataclass
class FetchResult:
    """Result of fetching one parish bulletin."""
    key: str
    display_name: str
    status: str             # "ok" | "error" | "html_link"
    url: str = ""           # URL fetched (or html link URL)
    file_path: Optional[Path] = None
    file_type: str = ""     # "pdf" | "docx_to_pdf" | "image_to_pdf" | "html_link"
    error: str = ""

    # Legacy compat — old code used .parish
    @property
    def parish(self) -> str:
        return self.key


# ---------------------------------------------------------------------------
# Evidence file parser
# ---------------------------------------------------------------------------

def _url_to_key(url: str, header_name: str = "") -> str:
    """Derive a stable parish key from a URL (domain-based)."""
    parsed = urlparse(url)
    hostname = re.sub(r"^www\d*\.", "", parsed.netloc.lower())

    # WordPress CDN (i0.wp.com, i1.wp.com, …): real domain is first path segment
    if re.search(r"\bi\d+\.wp\.com\b", hostname):
        path_parts = parsed.path.strip("/").split("/")
        if path_parts:
            real_domain = re.sub(r"^www\d*\.", "", path_parts[0].lower())
            parts = real_domain.split(".")
            if len(parts) >= 2:
                return parts[0]

    # Other CDN / Google Drive: use header name
    if any(cdn in hostname for cdn in ("filesafe.space", "google.com")):
        if header_name:
            return re.sub(r"[^a-z0-9]", "", header_name.lower().split("(")[0].strip())
        return re.sub(r"[^a-z0-9]", "", hostname.split(".")[0])

    parts = hostname.split(".")
    return parts[0] if parts else hostname


def parse_evidence_file(diocese: str, parishes_dir: Path | None = None) -> list[ParishEntry]:
    """
    Parse parishes/{diocese}_bulletin_urls.txt into a list of ParishEntry objects.

    The file groups entries by parish with ``# --- Name ---`` headers.
    Pattern comments (``# Pattern A:``, ``# html_link:``, etc.) drive the
    URL rewrite strategy.  The first non-comment URL is used as example_url.
    """
    if parishes_dir is None:
        parishes_dir = PARISHES_DIR
    path = parishes_dir / f"{diocese}_bulletin_urls.txt"
    if not path.exists():
        raise FileNotFoundError(f"Evidence file not found: {path}")

    entries: list[ParishEntry] = []

    # Current parish state
    cur_name: Optional[str] = None
    cur_key_override: Optional[str] = None
    cur_pattern: Optional[str] = None
    cur_is_html_link: bool = False
    cur_is_image: bool = False
    cur_is_docx: bool = False
    cur_urls: list[str] = []

    def _flush() -> None:
        nonlocal cur_name, cur_key_override, cur_pattern, cur_is_html_link
        nonlocal cur_is_image, cur_is_docx, cur_urls

        if not cur_urls:
            cur_name = cur_key_override = cur_pattern = None
            cur_is_html_link = cur_is_image = cur_is_docx = False
            return

        example_url = cur_urls[0]

        # Key derivation
        key = cur_key_override or _url_to_key(example_url, cur_name or "")

        # Determine content type
        url_lower = example_url.lower().split("?")[0]
        if cur_pattern == "clonleigh":
            # Clonleigh: calculate URL via clonleigh pattern but treat as html_link
            # (the HTML bulletin page URL is returned as a clickable link)
            content_type = "html_link"
            pattern = "clonleigh"
        elif cur_is_html_link or cur_pattern == "html_link":
            content_type = "html_link"
            # Preserve any explicitly-set date pattern (e.g. Pattern D, clonleigh) so
            # date math can still be applied when building the html_link URL.
            pattern = cur_pattern or "html_link"
        elif cur_is_image or url_lower.endswith((".jpg", ".jpeg", ".png")):
            content_type = "image"
            pattern = cur_pattern or "F"
        elif cur_is_docx or url_lower.endswith(".docx"):
            content_type = "docx"
            pattern = cur_pattern or "B"
        else:
            content_type = "pdf"
            pattern = cur_pattern or "A"

        entries.append(ParishEntry(
            key=key,
            display_name=cur_name or key,
            pattern=pattern,
            content_type=content_type,
            example_url=example_url,
            all_urls=cur_urls[:],
        ))

        cur_name = cur_key_override = cur_pattern = None
        cur_is_html_link = cur_is_image = cur_is_docx = False
        cur_urls = []

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("# ---"):
            _flush()
            m = re.match(r"#\s*---\s*(.+?)\s*---", line)
            if m:
                cur_name = m.group(1)
            continue

        if line.startswith("#"):
            ll = line.lower()
            if ll.startswith("# key:"):
                cur_key_override = line.split(":", 1)[1].strip()
            # Check multi-word patterns BEFORE single-letter patterns to avoid
            # substring collisions (e.g. "pattern clonleigh" contains "pattern c")
            elif "pattern greenlough" in ll:
                cur_pattern = "greenlough"
            elif "pattern clonleigh" in ll:
                cur_pattern = "clonleigh"
            elif re.search(r"pattern\s+a\b", ll):
                cur_pattern = "A"
            elif re.search(r"pattern\s+b\b", ll):
                cur_pattern = "B"
            elif re.search(r"pattern\s+c\b", ll):
                cur_pattern = "C"
            elif re.search(r"pattern\s+d\b", ll):
                cur_pattern = "D"
            elif re.search(r"pattern\s+e\b", ll):
                cur_pattern = "E"
            elif re.search(r"pattern\s+f\b", ll) or ("static" in ll and "pattern" in ll):
                cur_pattern = "F"
            elif re.search(r"pattern\s+h\b", ll):
                cur_pattern = "H"
            elif "html_link" in ll or ("html only" in ll and "pattern" not in ll):
                cur_is_html_link = True
                if cur_pattern is None:
                    cur_pattern = "html_link"
            elif "jpeg" in ll or ("image" in ll and "bulletin" in ll):
                cur_is_image = True
            elif "docx" in ll or "word document" in ll:
                cur_is_docx = True
            continue

        if line.startswith("http"):
            cur_urls.append(line)

    _flush()
    return entries


# ---------------------------------------------------------------------------
# URL calculation
# ---------------------------------------------------------------------------

def calculate_url(entry: ParishEntry, target: date) -> str:
    """Calculate this week's bulletin URL for the given parish entry."""
    url = entry.example_url
    pattern = entry.pattern

    if pattern == "html_link":
        return url
    if pattern == "F":
        # Static URL — download as-is each week
        return url
    if pattern == "greenlough":
        result = rewrite_greenlough_url(url, target)
        return result if result else url
    if pattern == "clonleigh":
        return rewrite_clonleigh_url(target)
    if pattern == "H":
        return rewrite_newsletter_number_url(url)
    # Patterns A, B, C, D, E (and G) — generic date rewrite
    return rewrite_date_url(url, target)


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------

def _is_real_pdf(path: Path, tag: str = "") -> bool:
    """Return True only if path is a valid PDF of at least MIN_PDF_BYTES."""
    if not is_valid_pdf(path):
        return False
    try:
        size = path.stat().st_size
    except OSError:
        return False
    if size < MIN_PDF_BYTES:
        print(
            f"  🗑️  Discarding tiny PDF{(' for ' + tag) if tag else ''}: "
            f"{size:,} bytes < {MIN_PDF_BYTES // 1000} KB"
        )
        return False
    return True


def _rewrite_gdrive_url(url: str) -> str:
    """Convert a Google Drive viewer URL to a direct-download URL.

    Transforms ``https://drive.google.com/file/d/FILE_ID/view[?...]``
    into ``https://drive.usercontent.google.com/download?id=FILE_ID&export=download``
    so that Playwright can download the file directly without hitting the
    HTML preview page.
    """
    m = re.search(r"drive\.google\.com/file/d/([^/?#]+)", url)
    if m:
        file_id = m.group(1)
        return (
            f"https://drive.usercontent.google.com/download"
            f"?id={file_id}&export=download"
        )
    return url


def _is_pdf_content(data: bytes) -> bool:
    """Return True if *data* starts with the PDF magic bytes ``%PDF``."""
    return data[:4] == b"%PDF"


async def _download_pdf(url: str, dest: Path, browser: Browser) -> None:
    """Download a PDF via a headless page."""
    # Convert Google Drive viewer links to direct-download URLs
    url = _rewrite_gdrive_url(url)

    context = await browser.new_context()
    try:
        # Attempt 1: navigate and expect a file download (Content-Disposition: attachment)
        _nav_response = None
        try:
            async with context.expect_download(timeout=PAGE_LOAD_TIMEOUT_MS) as dl_info:
                page = await context.new_page()
                _nav_response = await page.goto(
                    url, timeout=PAGE_LOAD_TIMEOUT_MS, wait_until="commit"
                )
            download = await dl_info.value
            await download.save_as(dest)
            return
        except Exception:
            pass

        # Attempt 2: capture PDF bytes from the navigation response body.
        # Handles servers (e.g. Three Patrons) that serve the PDF inline
        # rather than as an attachment download.
        if _nav_response is not None:
            try:
                body = await _nav_response.body()
                if _is_pdf_content(body):
                    dest.write_bytes(body)
                    return
            except Exception:
                pass

        # Attempt 3: direct HTTP request fallback
        page = await context.new_page()
        response = await page.request.get(url, timeout=PAGE_LOAD_TIMEOUT_MS)
        if response.ok:
            body = await response.body()
            # Accept the body if it is a valid PDF regardless of reported content-type
            if _is_pdf_content(body):
                dest.write_bytes(body)
                return
            content_type = response.headers.get("content-type", "")
            if "text/html" in content_type:
                raise RuntimeError(
                    f"Server returned HTML instead of a PDF for {url}"
                )
            dest.write_bytes(body)
        else:
            raise RuntimeError(f"HTTP {response.status} for {url}")
    except _TargetClosedError:
        raise
    finally:
        try:
            await context.close()
        except Exception:
            pass


async def _download_docx_as_pdf(url: str, dest: Path, browser: Browser) -> None:
    """Download a .docx file and convert it to PDF via LibreOffice or python-docx."""
    context = await browser.new_context()
    try:
        page = await context.new_page()
        response = await page.request.get(url, timeout=PAGE_LOAD_TIMEOUT_MS)
        if not response.ok:
            raise RuntimeError(f"HTTP {response.status} downloading DOCX from {url}")
        docx_bytes = await response.body()
    finally:
        try:
            await context.close()
        except Exception:
            pass

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        docx_file = tmp_path / "bulletin.docx"
        docx_file.write_bytes(docx_bytes)

        # Try LibreOffice conversion first
        try:
            result = subprocess.run(
                ["libreoffice", "--headless", "--convert-to", "pdf",
                 "--outdir", str(tmp_path), str(docx_file)],
                capture_output=True, timeout=60,
            )
            pdf_out = tmp_path / "bulletin.pdf"
            if result.returncode == 0 and pdf_out.exists():
                dest.write_bytes(pdf_out.read_bytes())
                return
        except (FileNotFoundError, subprocess.TimeoutExpired):
            print("  ℹ️  LibreOffice not available or timed out; falling back to python-docx converter")

        # Fallback: python-docx + reportlab
        try:
            import docx as _docx  # type: ignore[import]
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib.units import cm
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

            doc = _docx.Document(str(docx_file))
            text_lines = [p.text for p in doc.paragraphs if p.text.strip()]
            text = "\n".join(text_lines)
            if not text.strip():
                raise RuntimeError("DOCX has no text content")

            styles = getSampleStyleSheet()
            pdf_doc = SimpleDocTemplate(
                str(dest), pagesize=A4,
                topMargin=2 * cm, bottomMargin=2 * cm,
                leftMargin=2.5 * cm, rightMargin=2.5 * cm,
            )
            story = []
            for line in text.split("\n"):
                line = line.strip()
                if not line:
                    story.append(Spacer(1, 0.2 * cm))
                    continue
                safe = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                try:
                    story.append(Paragraph(safe, styles["Normal"]))
                except Exception:
                    pass
            pdf_doc.build(story)
            return
        except ImportError:
            pass

        raise RuntimeError(
            f"Could not convert DOCX to PDF for {url} — "
            "LibreOffice not installed and python-docx fallback failed"
        )


async def _download_image_as_pdf(url: str, dest: Path, browser: Browser) -> None:
    """Download a JPEG/PNG image and convert it to a single-page PDF."""
    from PIL import Image  # type: ignore[import]
    import io

    context = await browser.new_context()
    try:
        page = await context.new_page()
        response = await page.request.get(url, timeout=PAGE_LOAD_TIMEOUT_MS)
        if not response.ok:
            raise RuntimeError(f"HTTP {response.status} downloading image from {url}")
        img_bytes = await response.body()
    finally:
        try:
            await context.close()
        except Exception:
            pass

    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    img.save(str(dest), "PDF", resolution=150)


# ---------------------------------------------------------------------------
# Core fetch logic
# ---------------------------------------------------------------------------

async def _fetch_entry(
    entry: ParishEntry,
    output_dir: Path,
    target: date,
    browser: Browser,
) -> FetchResult:
    """Fetch one parish bulletin — no retries, called by fetch_parish."""
    output_dir.mkdir(parents=True, exist_ok=True)
    key = entry.key

    # html_link parishes: return URL (possibly calculated) without downloading
    if entry.content_type == "html_link":
        # Apply date math for any parish with a real date pattern (A–H, greenlough, etc.).
        # Only static patterns ("html_link", "F") return the example URL as-is.
        url = calculate_url(entry, target) if entry.pattern not in ("html_link", "F") else entry.example_url
        return FetchResult(
            key=key,
            display_name=entry.display_name,
            status="html_link",
            url=url,
            file_type="html_link",
        )

    # Calculate the predicted URL for this week
    target_url = calculate_url(entry, target)

    # Build fallback candidates:
    # - predicted target URL
    # - last Sunday's URL (target - 7 days)
    fallback_candidates: list[str] = [target_url]
    if entry.pattern == "H":
        # Pattern H requires the slug after the bulletin number — the server
        # returns 403 without it.  Try the current example_url (with slug)
        # FIRST, then fall back to the incremented number URL (no slug).
        fallback_candidates.insert(0, entry.example_url)
    elif entry.pattern not in ("F", "clonleigh", "html_link"):
        last_sunday_url = rewrite_date_url(entry.example_url, target - timedelta(days=7))
        if last_sunday_url != target_url and last_sunday_url != entry.example_url:
            fallback_candidates.append(last_sunday_url)
        # For greenlough, also try the last-Sunday liturgical URL
        if entry.pattern == "greenlough":
            gs = rewrite_greenlough_url(entry.example_url, target - timedelta(days=7))
            if gs and gs not in fallback_candidates:
                fallback_candidates.append(gs)
        # Also try the literal example_url as last resort
        if entry.example_url not in fallback_candidates:
            fallback_candidates.append(entry.example_url)
    elif entry.pattern == "clonleigh":
        # Also try last week's clonleigh URL
        last_week = rewrite_clonleigh_url(target - timedelta(days=7))
        if last_week != target_url:
            fallback_candidates.append(last_week)

    dest = output_dir / safe_filename(key, ".pdf")
    last_err = "No valid content found"

    for candidate in fallback_candidates:
        try:
            # Encode any spaces in the URL (e.g. "NEWSLETTER 12-4-26.docx") so the
            # HTTP request succeeds.  Keep the original for display/logging.
            candidate_encoded = candidate.replace(" ", "%20")
            if entry.content_type == "image":
                await _download_image_as_pdf(candidate_encoded, dest, browser)
                if _is_real_pdf(dest, key):
                    return FetchResult(
                        key=key, display_name=entry.display_name,
                        status="ok", url=candidate,
                        file_path=dest, file_type="image_to_pdf",
                    )
            elif entry.content_type == "docx":
                await _download_docx_as_pdf(candidate_encoded, dest, browser)
                if _is_real_pdf(dest, key):
                    return FetchResult(
                        key=key, display_name=entry.display_name,
                        status="ok", url=candidate,
                        file_path=dest, file_type="docx_to_pdf",
                    )
            else:
                await _download_pdf(candidate_encoded, dest, browser)
                if _is_real_pdf(dest, key):
                    if candidate != target_url:
                        print(f"  📅 Used fallback URL for {key}: {candidate}")
                    return FetchResult(
                        key=key, display_name=entry.display_name,
                        status="ok", url=candidate,
                        file_path=dest, file_type="pdf",
                    )
        except Exception as exc:
            last_err = str(exc)
            print(f"  ↩️  {key}: {candidate} failed: {last_err}")
        finally:
            if dest.exists() and not _is_real_pdf(dest):
                dest.unlink(missing_ok=True)

    return FetchResult(
        key=key, display_name=entry.display_name,
        status="error", url=target_url, error=last_err,
    )


async def fetch_parish(
    entry: ParishEntry,
    output_dir: Path,
    target: date,
    browser: Browser,
) -> FetchResult:
    """Fetch one parish bulletin with retries and a total timeout."""
    # html_link: instant, no timeout needed
    if entry.content_type == "html_link":
        url = calculate_url(entry, target) if entry.pattern not in ("html_link", "F") else entry.example_url
        return FetchResult(
            key=entry.key,
            display_name=entry.display_name,
            status="html_link",
            url=url,
            file_type="html_link",
        )

    last_error = ""
    for attempt in range(_MAX_ATTEMPTS):
        try:
            async with asyncio.timeout(TOTAL_TIMEOUT_S):
                result = await _fetch_entry(entry, output_dir, target, browser)
            if result.status == "ok":
                return result
            last_error = result.error
        except TimeoutError:
            last_error = "Total timeout exceeded"
        except Exception as exc:
            last_error = str(exc)

        if attempt < _MAX_ATTEMPTS - 1:
            print(
                f"  ↩️  Retrying {entry.key} "
                f"(attempt {attempt + 2}/{_MAX_ATTEMPTS}): {last_error}"
            )
            await asyncio.sleep(_RETRY_DELAY_S)

    return FetchResult(
        key=entry.key, display_name=entry.display_name,
        status="error",
        url=calculate_url(entry, target),
        error=last_error,
    )


async def fetch_all(
    entries: list[ParishEntry],
    output_dir: Path,
    target: date,
) -> list[FetchResult]:
    """Fetch all parishes concurrently, bounded by CONCURRENCY."""
    sem = asyncio.Semaphore(CONCURRENCY)

    async def _bounded(e: ParishEntry, browser: Browser) -> FetchResult:
        async with sem:
            return await fetch_parish(e, output_dir, target, browser)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        tasks = [_bounded(e, browser) for e in entries]
        results = list(await asyncio.gather(*tasks, return_exceptions=True))

        await asyncio.sleep(_PLAYWRIGHT_SHUTDOWN_DELAY_S)
        try:
            await browser.close()
        except Exception:
            pass

    final: list[FetchResult] = []
    for entry, result in zip(entries, results):
        if isinstance(result, Exception):
            final.append(FetchResult(
                key=entry.key, display_name=entry.display_name,
                status="error",
                url=calculate_url(entry, target),
                error=str(result),
            ))
        else:
            final.append(result)

    return final
