"""
fetcher.py — Stage 1: Download PDFs using Playwright.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

from playwright.async_api import (
    Browser,
    async_playwright,
    TimeoutError as PlaywrightTimeout,
)
try:
    from playwright._impl._errors import TargetClosedError as _TargetClosedError
except Exception:
    _TargetClosedError = Exception  # type: ignore[assignment,misc]

from .config import BULLETIN_KEYWORDS, CONCURRENCY, PAGE_LOAD_TIMEOUT_MS, TOTAL_TIMEOUT_S

# Seconds to wait after all tasks finish before closing the browser, to allow
# any lingering Playwright background futures to settle gracefully.
_PLAYWRIGHT_SHUTDOWN_DELAY_S: float = 0.5
from .utils import (
    date_variants,
    extract_date_from_string,
    is_valid_pdf,
    parish_name_from_url,
    rewrite_date_url,
    safe_filename,
)

# Seconds to wait between retry attempts
_RETRY_DELAY_S: float = 3.0
# Number of attempts (1 original + 1 retry)
_MAX_ATTEMPTS: int = 2


@dataclass
class FetchResult:
    url: str
    parish: str
    status: str          # "ok" | "error"
    file_path: Optional[Path] = None
    file_type: str = ""  # "pdf"
    error: str = ""
    candidate_urls: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _url_ends_in_pdf(url: str) -> bool:
    path = urlparse(url).path.lower()
    return path.endswith(".pdf")


def _score_link(href: str, text: str, target: date) -> int:
    """
    Score a candidate PDF link.  Higher is better.
    Returns -1 if the link should be completely ignored.

    A link is considered a candidate if:
    - The URL contains '.pdf', OR
    - The link text contains a bulletin keyword (e.g. "bulletin", "newsletter")
      which suggests the link may be a redirect to a PDF.
    """
    combined = (href + " " + text).lower()
    score = 0

    has_pdf_in_url = ".pdf" in href.lower()
    has_bulletin_text = any(kw in text.lower() for kw in BULLETIN_KEYWORDS)

    # Must be a likely PDF/bulletin link
    if not has_pdf_in_url and not has_bulletin_text:
        return -1

    # PDF in URL is a strong signal
    if has_pdf_in_url:
        score += 20

    # Keyword match in href or text
    for kw in BULLETIN_KEYWORDS:
        if kw in combined:
            score += 10

    # Date patterns in this week
    for variant in date_variants(target):
        if variant in href or variant in text:
            score += 50

    # Generic date in filename → mild boost
    if extract_date_from_string(href) is not None:
        score += 5

    return score


def _pick_best_pdf(links: list[tuple[str, str]], target: date) -> Optional[str]:
    """Return the href of the best PDF link, or None."""
    scored = []
    for href, text in links:
        s = _score_link(href, text, target)
        if s >= 0:
            scored.append((s, href))
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


async def _download_pdf(url: str, dest: Path, browser: Browser) -> None:
    """Download a PDF via a headless page (handles JS redirects, cookies, etc.)."""
    context = await browser.new_context()
    try:
        async with context.expect_download(timeout=PAGE_LOAD_TIMEOUT_MS) as dl_info:
            page = await context.new_page()
            await page.goto(url, timeout=PAGE_LOAD_TIMEOUT_MS, wait_until="commit")
        download = await dl_info.value
        await download.save_as(dest)
    except Exception:
        # Fallback: direct HTTP download via fetch API
        try:
            page = await context.new_page()
            response = await page.request.get(url, timeout=PAGE_LOAD_TIMEOUT_MS)
            if response.ok:
                dest.write_bytes(await response.body())
            else:
                raise RuntimeError(f"HTTP {response.status} for {url}")
        except _TargetClosedError:
            raise
    finally:
        try:
            await context.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def fetch_parish(
    url: str,
    output_dir: Path,
    target: date,
    browser: Browser,
) -> FetchResult:
    """
    Fetch bulletins/screenshots for a single parish URL.
    Retries once on failure before returning an error result.
    """
    parish = parish_name_from_url(url)

    last_error: str = ""
    for attempt in range(_MAX_ATTEMPTS):
        try:
            async with asyncio.timeout(TOTAL_TIMEOUT_S):
                result = await _fetch_inner(url, parish, output_dir, target, browser)
            if result.status == "ok":
                return result
            # _fetch_inner returned an error result (e.g. no PDF found) — retry
            last_error = result.error
        except TimeoutError:
            last_error = "Total timeout exceeded"
        except Exception as exc:
            last_error = str(exc)

        if attempt < _MAX_ATTEMPTS - 1:
            print(f"  ↩️  Retrying {parish} (attempt {attempt + 2}/{_MAX_ATTEMPTS}): {last_error}")
            await asyncio.sleep(_RETRY_DELAY_S)

    return FetchResult(url=url, parish=parish, status="error", error=last_error)


async def _fetch_inner(
    url: str,
    parish: str,
    output_dir: Path,
    target: date,
    browser: Browser,
) -> FetchResult:
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- Direct PDF URL ---
    if _url_ends_in_pdf(url):
        # Try to rewrite date to target week
        rewritten = rewrite_date_url(url, target)
        if rewritten != url:
            print(f"  🔗 Rewrote URL for {parish}: {url} → {rewritten}")
        dest = output_dir / safe_filename(parish, ".pdf")
        await _download_pdf(rewritten, dest, browser)
        if not is_valid_pdf(dest):
            dest.unlink(missing_ok=True)
            return FetchResult(url=rewritten, parish=parish, status="error",
                               error="Downloaded file is not a valid PDF")
        return FetchResult(url=rewritten, parish=parish, status="ok",
                           file_path=dest, file_type="pdf")

    # --- Load page, look for PDF links ---
    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    )
    try:
        page = await context.new_page()
        try:
            await page.goto(url, timeout=PAGE_LOAD_TIMEOUT_MS, wait_until="networkidle")
        except PlaywrightTimeout:
            # networkidle timed out — page still loaded enough, continue
            pass

        page_url = page.url

        # Collect all <a> links
        anchors = await page.eval_on_selector_all(
            "a[href]",
            "els => els.map(el => [el.href, el.innerText.trim()])",
        )

        # Collect <iframe src> attributes
        iframes = await page.eval_on_selector_all(
            "iframe[src]",
            "els => els.map(el => [el.src, ''])",
        )

        # Build absolute hrefs, collect PDF candidates and bulletin-keyword links
        links: list[tuple[str, str]] = []
        for href, text in anchors:
            if not href:
                continue
            abs_href = urljoin(page_url, href)
            # Include if URL suggests a PDF or text suggests a bulletin
            if ".pdf" in abs_href.lower() or any(
                kw in text.lower() for kw in BULLETIN_KEYWORDS
            ):
                links.append((abs_href, text))

        # Also include iframes that reference PDFs or bulletin keywords
        for src, _ in iframes:
            if not src:
                continue
            abs_src = urljoin(page_url, src)
            if ".pdf" in abs_src.lower() or any(
                kw in abs_src.lower() for kw in BULLETIN_KEYWORDS
            ):
                links.append((abs_src, "iframe"))

        best_pdf = _pick_best_pdf(links, target)

        if best_pdf:
            dest = output_dir / safe_filename(parish, ".pdf")
            await _download_pdf(best_pdf, dest, browser)
            if not is_valid_pdf(dest):
                dest.unlink(missing_ok=True)
                result = FetchResult(
                    url=url, parish=parish, status="error",
                    error="Downloaded file is not a valid PDF",
                    candidate_urls=[h for h, _ in links],
                )
            else:
                result = FetchResult(
                    url=url, parish=parish, status="ok",
                    file_path=dest, file_type="pdf",
                    candidate_urls=[h for h, _ in links],
                )
        else:
            # --- No PDF found → report error ---
            result = FetchResult(
                url=url, parish=parish, status="error",
                error="No PDF found",
                candidate_urls=[h for h, _ in links],
            )

    finally:
        await context.close()

    return result


# ---------------------------------------------------------------------------
# Batch runner
# ---------------------------------------------------------------------------

async def fetch_all(
    urls: list[str],
    output_dir: Path,
    target: date,
) -> list[FetchResult]:
    """Fetch all parishes concurrently, bounded by CONCURRENCY."""
    sem = asyncio.Semaphore(CONCURRENCY)

    async def _bounded(url: str, browser: Browser) -> FetchResult:
        async with sem:
            return await fetch_parish(url, output_dir, target, browser)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        tasks = [_bounded(url, browser) for url in urls]
        results = list(await asyncio.gather(*tasks, return_exceptions=True))

        # Give pending Playwright futures a moment to settle
        await asyncio.sleep(_PLAYWRIGHT_SHUTDOWN_DELAY_S)

        try:
            await browser.close()
        except Exception:
            pass

    # Convert any exceptions from gather into error FetchResults
    final_results: list[FetchResult] = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            parish = parish_name_from_url(urls[i]) if i < len(urls) else "unknown"
            final_results.append(FetchResult(
                url=urls[i] if i < len(urls) else "",
                parish=parish,
                status="error",
                error=str(r),
            ))
        else:
            final_results.append(r)

    return final_results
