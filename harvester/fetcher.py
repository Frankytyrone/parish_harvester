"""
fetcher.py — Stage 1: Download PDFs or screenshots using Playwright.
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

from .config import BULLETIN_KEYWORDS, CONCURRENCY, PAGE_LOAD_TIMEOUT_MS, TOTAL_TIMEOUT_S
from .utils import (
    date_variants,
    extract_date_from_string,
    parish_name_from_url,
    rewrite_date_url,
    safe_filename,
)


@dataclass
class FetchResult:
    url: str
    parish: str
    status: str          # "ok" | "error"
    file_path: Optional[Path] = None
    file_type: str = ""  # "pdf" | "png"
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
    """
    combined = (href + " " + text).lower()
    score = 0

    # Must at least be a PDF
    if ".pdf" not in href.lower():
        return -1

    # Keyword match
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
        page = await context.new_page()
        response = await page.request.get(url, timeout=PAGE_LOAD_TIMEOUT_MS)
        if response.ok:
            dest.write_bytes(await response.body())
        else:
            raise RuntimeError(f"HTTP {response.status} for {url}")
    finally:
        await context.close()


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
    Returns a FetchResult describing what was saved (or what error occurred).
    """
    parish = parish_name_from_url(url)

    try:
        async with asyncio.timeout(TOTAL_TIMEOUT_S):
            return await _fetch_inner(url, parish, output_dir, target, browser)
    except TimeoutError:
        return FetchResult(url=url, parish=parish, status="error",
                           error="Total timeout exceeded")
    except Exception as exc:
        return FetchResult(url=url, parish=parish, status="error", error=str(exc))


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
        dest = output_dir / safe_filename(parish, ".pdf")
        await _download_pdf(rewritten, dest, browser)
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

        # Collect all <a> links
        anchors = await page.eval_on_selector_all(
            "a[href]",
            "els => els.map(el => [el.href, el.innerText.trim()])",
        )

        # Build absolute hrefs, filter to PDF candidates
        page_url = page.url
        links: list[tuple[str, str]] = []
        for href, text in anchors:
            if not href:
                continue
            abs_href = urljoin(page_url, href)
            if ".pdf" in abs_href.lower():
                links.append((abs_href, text))

        best_pdf = _pick_best_pdf(links, target)

        if best_pdf:
            dest = output_dir / safe_filename(parish, ".pdf")
            await _download_pdf(best_pdf, dest, browser)
            result = FetchResult(
                url=url, parish=parish, status="ok",
                file_path=dest, file_type="pdf",
                candidate_urls=[h for h, _ in links],
            )
        else:
            # --- No PDF found → full-page screenshot ---
            dest = output_dir / safe_filename(parish, ".png")
            await page.screenshot(path=str(dest), full_page=True)
            result = FetchResult(
                url=url, parish=parish, status="ok",
                file_path=dest, file_type="png",
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
    results: list[FetchResult] = []

    async def _bounded(url: str, browser: Browser) -> FetchResult:
        async with sem:
            return await fetch_parish(url, output_dir, target, browser)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        tasks = [_bounded(url, browser) for url in urls]
        results = await asyncio.gather(*tasks)
        await browser.close()

    return list(results)
