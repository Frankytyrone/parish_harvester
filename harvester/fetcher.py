"""
fetcher.py — Stage 1: Download PDFs using Playwright.

Supports two modes:
  - PDF bulletin  : find a PDF link on (or linked from) the parish homepage and
                    download it.
  - HTML bulletin : for sites like Ballinascreen/Wix where the bulletin is
                    published as an HTML page, scrape the text and convert it to
                    a PDF with reportlab.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse, parse_qs

from playwright.async_api import (
    Browser,
    Page,
    Response,
    async_playwright,
    TimeoutError as PlaywrightTimeout,
)
try:
    from playwright._impl._errors import TargetClosedError as _TargetClosedError
except Exception:
    _TargetClosedError = Exception  # type: ignore[assignment,misc]

from .config import (
    BULLETIN_IMAGE_KEYWORDS,
    BULLETIN_KEYWORDS,
    CONCURRENCY,
    JUNK_KEYWORDS,
    PAGE_LOAD_TIMEOUT_MS,
    SUB_PAGE_KEYWORDS,
    TOTAL_TIMEOUT_S,
    WIX_SELECTORS,
)

# Seconds to wait after all tasks finish before closing the browser, to allow
# any lingering Playwright background futures to settle gracefully.
_PLAYWRIGHT_SHUTDOWN_DELAY_S: float = 0.5
from .utils import (
    date_variants,
    extract_date_from_slug,
    extract_date_from_string,
    is_valid_pdf,
    parish_name_from_url,
    rewrite_date_url,
    rewrite_slug_url,
    safe_filename,
)

# Seconds to wait between retry attempts
_RETRY_DELAY_S: float = 3.0
# Number of attempts (1 original + 1 retry)
_MAX_ATTEMPTS: int = 2

# Minimum PDF size (bytes). Files smaller than this are almost always HTML
# error pages disguised as PDFs (e.g. a "404 Not Found" page returned with
# a .pdf Content-Disposition header).  50 KB is well below the size of even
# the smallest single-page church bulletin.
_MIN_PDF_BYTES: int = 50_000

# Wix page-source signatures used to identify Wix sites
_WIX_SIGNATURES: tuple[str, ...] = (
    "wix-site",
    'data-testid="site-root"',
    "WixSite",
    "_wix_",
)


@dataclass
class FetchResult:
    url: str
    parish: str
    status: str          # "ok" | "error"
    file_path: Optional[Path] = None
    file_type: str = ""  # "pdf" | "html_to_pdf"
    error: str = ""
    candidate_urls: list[str] = field(default_factory=list)
    site_type: Optional[str] = None  # "wix" | None
    source_url: str = ""             # URL where the content was actually found


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _url_ends_in_pdf(url: str) -> bool:
    path = urlparse(url).path.lower()
    return path.endswith(".pdf")


def _is_real_pdf(path: Path, parish: str = "", url: str = "") -> bool:
    """
    Return True if *path* is a valid PDF **and** is at least 30 KB in size.

    Files that are valid PDF magic-bytes but smaller than 30 KB are almost
    always HTML error pages (e.g. "404 Not Found") returned by the server and
    saved with a ``.pdf`` extension.  Rule 1 of AI_HISTORY.md: never accept a
    PDF smaller than 30 KB.
    """
    if not is_valid_pdf(path):
        return False
    try:
        size = path.stat().st_size
    except OSError:
        return False
    if size < _MIN_PDF_BYTES:
        tag = f" for {parish}" if parish else ""
        src = f" ({url})" if url else ""
        print(
            f"  🗑️  Discarding tiny PDF{tag}{src}: "
            f"{size:,} bytes < 50 KB — likely a fake PDF / HTML error page"
        )
        return False
    return True


def _score_link(href: str, text: str, target: date) -> int:
    """
    Score a candidate PDF link.  Higher is better.
    Returns -1 if the link should be completely ignored.
    """
    combined = (href + " " + text).lower()

    # Reject links that contain junk keywords
    if any(kw in combined for kw in JUNK_KEYWORDS):
        return -1

    score = 0

    has_pdf_in_url = ".pdf" in href.lower()
    has_bulletin_text = any(kw in text.lower() for kw in BULLETIN_KEYWORDS)

    if not has_pdf_in_url and not has_bulletin_text:
        return -1

    if has_pdf_in_url:
        score += 20

    for kw in BULLETIN_KEYWORDS:
        if kw in combined:
            score += 10

    for variant in date_variants(target):
        if variant in href or variant in text:
            score += 50

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


def _pick_top_pdfs(links: list[tuple[str, str]], target: date, n: int = 5) -> list[str]:
    """Return the top-*n* PDF link hrefs sorted best-first.

    Tries up to *n* candidates so that the caller can fall back to the next
    best link when the highest-scoring one turns out to be a junk/tiny file.

    Returns fewer than *n* items if there are not enough viable candidates,
    or an empty list if no links score >= 0.
    """
    scored = []
    for href, text in links:
        s = _score_link(href, text, target)
        if s >= 0:
            scored.append((s, href))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [href for _, href in scored[:n]]


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
        try:
            page = await context.new_page()
            response = await page.request.get(url, timeout=PAGE_LOAD_TIMEOUT_MS)
            if response.ok:
                content_type = response.headers.get("content-type", "")
                if "text/html" in content_type:
                    raise RuntimeError(
                        f"Server returned HTML instead of a PDF for {url} "
                        f"(Content-Type: {content_type})"
                    )
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


def _text_to_pdf(text: str, dest: Path, title: str = "", source_url: str = "") -> None:
    """
    Convert plain text to a single PDF file at *dest* using reportlab.

    :param text: The raw text content to render (newlines become paragraph breaks).
    :param dest: Output path for the generated PDF file.
    :param title: Optional title displayed at the top of the first page.
    :param source_url: Optional source URL printed below the title for reference.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(
        str(dest),
        pagesize=A4,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        leftMargin=2.5 * cm,
        rightMargin=2.5 * cm,
    )

    story = []
    if title:
        story.append(Paragraph(title, styles["Title"]))
        story.append(Spacer(1, 0.5 * cm))
    if source_url:
        safe_url = (
            source_url
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        story.append(Paragraph(f"Source: {safe_url}", styles["Normal"]))
        story.append(Spacer(1, 0.5 * cm))

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            story.append(Spacer(1, 0.2 * cm))
            continue
        line = (
            line.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        try:
            story.append(Paragraph(line, styles["Normal"]))
        except Exception:
            try:
                plain = re.sub(r"<[^>]+>", "", line)
                story.append(Paragraph(plain, styles["Normal"]))
            except Exception:
                pass

    doc.build(story)


async def _is_wix_page(page: Page, response: Response | None = None) -> bool:
    """Return True if the current page appears to be built with Wix."""
    if response:
        for header_name in response.headers:
            if header_name.lower().startswith("x-wix-"):
                return True
    try:
        content = await page.content()
        if any(sig in content for sig in _WIX_SIGNATURES):
            return True
    except Exception:
        pass
    return False


async def _find_bulletin_image_link(page: Page, page_url: str) -> Optional[str]:
    """
    Look for a link to an HTML bulletin page by checking anchor text AND the
    ``alt`` attribute of any ``<img>`` elements nested inside the anchor.

    Returns the absolute URL of the first matching same-domain, non-PDF link.
    """
    try:
        anchor_data = await page.eval_on_selector_all(
            "a[href]",
            """els => els.map(el => {
                const imgs = el.querySelectorAll('img');
                const imgAlts = Array.from(imgs).map(i => i.alt || '').join(' ');
                return [el.href, el.innerText.trim(), imgAlts.trim()];
            })""",
        )
    except Exception:
        return None

    base_domain = urlparse(page_url).netloc

    for href, text, img_alts in anchor_data:
        if not href:
            continue
        combined = (text + " " + img_alts).lower()
        if any(kw in combined for kw in BULLETIN_IMAGE_KEYWORDS):
            abs_href = urljoin(page_url, href)
            if (
                ".pdf" not in abs_href.lower()
                and abs_href.rstrip("/") != page_url.rstrip("/")
                and urlparse(abs_href).netloc == base_domain
            ):
                return abs_href

    return None


async def _scrape_html_to_pdf(
    url: str,
    parish: str,
    output_dir: Path,
    browser: Browser,
    context,
    site_type: Optional[str] = None,
    target: Optional[date] = None,
) -> Optional[Path]:
    """
    Navigate to *url*, wait for JS rendering (Wix-aware), extract text, and
    write a PDF via reportlab.  Returns the saved Path or None.

    Before falling back to text extraction, the function scans the rendered
    HTML for any linked PDF files (e.g. bulletin listing pages that embed
    direct PDF download links) and tries to download the best match first.
    *target* is the target bulletin date used for link scoring; if omitted,
    today's date is used as a best-effort fallback.
    """
    html_page = None
    try:
        html_page = await context.new_page()
        response = None
        try:
            response = await html_page.goto(
                url, timeout=PAGE_LOAD_TIMEOUT_MS, wait_until="domcontentloaded"
            )
        except PlaywrightTimeout:
            pass

        # If the destination turned out to be a PDF, download it directly
        if response:
            ct = response.headers.get("content-type", "")
            final_url = html_page.url
            if ct.startswith("application/pdf") or _url_ends_in_pdf(final_url):
                dest = output_dir / safe_filename(parish, ".pdf")
                await _download_pdf(final_url, dest, browser)
                if _is_real_pdf(dest, parish, final_url):
                    return dest
                dest.unlink(missing_ok=True)
                return None

        # Auto-detect Wix if not already known
        if not site_type:
            if await _is_wix_page(html_page, response):
                site_type = "wix"

        # Wait for page to finish rendering
        if site_type == "wix":
            try:
                await html_page.wait_for_selector(
                    'div[data-testid="site-root"]', timeout=10_000
                )
            except Exception:
                try:
                    await html_page.wait_for_load_state("networkidle", timeout=15_000)
                except Exception:
                    pass
        else:
            try:
                await html_page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:
                pass

        # --- Scan the HTML page for direct PDF links before text extraction ---
        # This handles sites like stmarysparishcreggan.com/bulletins where the
        # bulletins listing page embeds links to actual PDF bulletin files.
        try:
            page_anchors = await html_page.eval_on_selector_all(
                "a[href]",
                "els => els.map(el => [el.href, el.innerText.trim()])",
            )
            pdf_links: list[tuple[str, str]] = []
            for href, link_text in page_anchors:
                if not href or ".pdf" not in href.lower():
                    continue
                abs_href = urljoin(url, href)
                pdf_links.append((abs_href, link_text))

            # Also collect <embed> and <object data> PDF sources on this page
            try:
                embed_srcs = await html_page.eval_on_selector_all(
                    "embed[src]", "els => els.map(el => [el.src, ''])"
                )
                object_srcs = await html_page.eval_on_selector_all(
                    "object[data]", "els => els.map(el => [el.data, ''])"
                )
                for src, _ in embed_srcs + object_srcs:
                    if src and ".pdf" in src.lower():
                        pdf_links.append((urljoin(url, src), "embed/object"))
            except Exception:
                pass

            if pdf_links:
                # Use the scoring function to pick the best candidates
                scoring_date = target if target is not None else date.today()
                if target is None:
                    print(f"  ⚠️  No target date provided to _scrape_html_to_pdf for {parish}; using today as fallback for PDF link scoring")
                top_candidates = _pick_top_pdfs(pdf_links, scoring_date, n=5)
                if not top_candidates:
                    # Fall back to any PDF link if scoring finds none
                    top_candidates = [href for href, _ in pdf_links[:5]]

                for pdf_url in top_candidates:
                    pdf_dest = output_dir / safe_filename(parish, ".pdf")
                    try:
                        await _download_pdf(pdf_url, pdf_dest, browser)
                        if _is_real_pdf(pdf_dest, parish, pdf_url):
                            print(f"  📎 Found PDF link in HTML page for {parish}: {pdf_url}")
                            return pdf_dest
                        pdf_dest.unlink(missing_ok=True)
                    except Exception as exc:
                        pdf_dest.unlink(missing_ok=True)
                        print(f"  ⚠️  PDF link in HTML page failed for {parish} ({pdf_url}): {exc}")
        except Exception:
            pass

        # Extract text — try specific selectors first, fall back to whole body
        text_content = ""
        for selector in WIX_SELECTORS:
            try:
                element = await html_page.query_selector(selector)
                if element:
                    t = await element.inner_text()
                    if len(t.strip()) > 100:
                        text_content = t
                        break
            except Exception:
                continue

        if not text_content.strip():
            try:
                text_content = await html_page.inner_text("body")
            except Exception:
                pass

        if not text_content.strip():
            return None

        dest = output_dir / safe_filename(parish, ".pdf")
        try:
            _text_to_pdf(
                text_content,
                dest,
                title=parish.replace("_", " ").title(),
                source_url=url,
            )
        except Exception as exc:
            print(f"  ⚠️  PDF build failed for {parish}: {exc}")
            dest.unlink(missing_ok=True)
            return None

        if dest.exists() and dest.stat().st_size > 0:
            return dest

        return None

    except Exception as exc:
        print(f"  ⚠️  HTML-to-PDF failed for {parish} ({url}): {exc}")
        return None
    finally:
        if html_page is not None:
            try:
                await html_page.close()
            except Exception:
                pass


async def _find_dated_bulletin_link(
    listing_url: str,
    target: date,
    context,
    base_domain: str,
) -> Optional[str]:
    """
    Load a bulletin listing page and return the link to the actual bulletin
    page whose URL slug date is closest to (and within 10 days of) *target*.

    Handles sites like Ballinascreen where clicking the bulletin image
    leads to a /latest-news listing page rather than the bulletin itself,
    and the actual bulletin is at a dated slug like
    ``ballinascreen-desertmartin-parishes-5_april_2026``.
    """
    page = None
    try:
        page = await context.new_page()
        try:
            await page.goto(
                listing_url, timeout=PAGE_LOAD_TIMEOUT_MS, wait_until="domcontentloaded"
            )
        except PlaywrightTimeout:
            pass

        anchors = await page.eval_on_selector_all(
            "a[href]",
            "els => els.map(el => [el.href, el.innerText.trim()])",
        )

        best_url: Optional[str] = None
        best_delta: Optional[int] = None

        for href, _ in anchors:
            if not href:
                continue
            abs_href = urljoin(listing_url, href)
            if urlparse(abs_href).netloc != base_domain:
                continue
            link_date = extract_date_from_slug(abs_href)
            if link_date is None:
                continue
            delta = (target - link_date).days
            if 0 <= delta <= 10:
                if best_delta is None or delta < best_delta:
                    best_delta = delta
                    best_url = abs_href

        return best_url
    except Exception:
        return None
    finally:
        if page is not None:
            try:
                await page.close()
            except Exception:
                pass




async def fetch_parish(
    url: str,
    output_dir: Path,
    target: date,
    browser: Browser,
    hint: Optional[dict] = None,
) -> FetchResult:
    """
    Fetch bulletin for a single parish URL.  Retries once on failure.

    *hint* is an optional dict from ``profiles.get_hint()`` that may contain
    ``last_success_method``, ``site_type``, etc.
    """
    parish = parish_name_from_url(url)

    last_error: str = ""
    for attempt in range(_MAX_ATTEMPTS):
        try:
            async with asyncio.timeout(TOTAL_TIMEOUT_S):
                result = await _fetch_inner(url, parish, output_dir, target, browser, hint=hint)
            if result.status == "ok":
                return result
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
    hint: Optional[dict] = None,
) -> FetchResult:
    output_dir.mkdir(parents=True, exist_ok=True)

    hint = hint or {}
    hint_site_type: Optional[str] = hint.get("site_type")
    fast_html_path: bool = hint.get("last_success_method") == "html_to_pdf"

    # --- Predictive URL Generator (Rule 2 / Rule 3 from AI_HISTORY.md) -------
    # If a previous successful download URL is stored, try to predict this
    # week's bulletin URL by date-shifting the stored URL before doing a full
    # site crawl.  rewrite_date_url() handles all known patterns:
    #   • Pattern A: DDMMYY / DDMMYYYY  (e.g. carndonaghparish.com/pdf/050426.pdf)
    #   • Pattern B: D-M-YY             (e.g. limavadyparish.org/onewebmedia/5-4-26.pdf)
    #   • Pattern C: ISO YYYY-MM-DD     (e.g. clonmanyparish.ie/2026/04/2026-04-12.pdf)
    #   • Pattern D: DD-Month-YYYY slug (e.g. bellaghyparish.com/wp-content/.../12-April-2026.pdf)
    #   • Pattern E: [YYYY-M-D]         (e.g. greenlough.com/newsletter/[2026-4-12].pdf)
    #   • Pattern F: static filename    (e.g. laveyparishbulletin.pdf - returned unchanged)
    # -------------------------------------------------------------------------
    last_success_url: Optional[str] = hint.get("last_success_url")
    if last_success_url and last_success_url != url:
        predicted_candidates: list[str] = []
        predicted = rewrite_date_url(last_success_url, target)
        if predicted != last_success_url:
            predicted_candidates.append(predicted)
        # If no date pattern was found in the stored URL (e.g. /current-newsletter/)
        # try it directly — it may be a stable weekly URL.
        if not predicted_candidates:
            predicted_candidates.append(last_success_url)

        dest = output_dir / safe_filename(parish, ".pdf")
        for candidate in predicted_candidates:
            print(f"  🔮 Predicting bulletin URL for {parish}: {candidate}")
            try:
                await _download_pdf(candidate, dest, browser)
                if _is_real_pdf(dest, parish, candidate):
                    print(f"  ✅ Predicted URL succeeded for {parish}")
                    return FetchResult(
                        url=url, parish=parish, status="ok",
                        file_path=dest, file_type="pdf",
                        source_url=candidate,
                    )
            except Exception as exc:
                print(f"  ⚠️  Predicted URL {candidate} failed for {parish}: {exc}")
            # Clean up any partial/invalid download before trying the next candidate
            dest.unlink(missing_ok=True)
        if predicted_candidates:
            print(f"  ↩️  Predicted URL(s) failed for {parish}, falling back to full site crawl")

    # --- Direct PDF URL ---
    if _url_ends_in_pdf(url):
        rewritten = rewrite_date_url(url, target)
        if rewritten != url:
            print(f"  🔗 Rewrote URL for {parish}: {url} → {rewritten}")

        # Build a list of candidate URLs: target date first, then last Sunday
        # (the most likely bulletin date), then the remaining days up to 10 days
        # back.  This ensures we try the most probable dates first.
        candidates = [rewritten]
        # Last Sunday is almost always the bulletin date — try it second
        last_sunday = rewrite_date_url(url, target - timedelta(days=7))
        if last_sunday not in candidates:
            candidates.append(last_sunday)
        for delta in range(1, 11):
            if delta == 7:
                continue  # already added above
            earlier = rewrite_date_url(url, target - timedelta(days=delta))
            if earlier not in candidates:
                candidates.append(earlier)

        dest = output_dir / safe_filename(parish, ".pdf")
        last_err = "No valid PDF found for any date candidate"
        for candidate in candidates:
            try:
                await _download_pdf(candidate, dest, browser)
            except Exception as exc:
                dest.unlink(missing_ok=True)
                last_err = str(exc)
                print(f"  ↩️  {parish}: {candidate} failed ({last_err}), trying next date...")
                continue
            if _is_real_pdf(dest, parish, candidate):
                if candidate != rewritten:
                    print(f"  📅 Used fallback date URL for {parish}: {candidate}")
                return FetchResult(url=candidate, parish=parish, status="ok",
                                   file_path=dest, file_type="pdf",
                                   source_url=candidate)
            dest.unlink(missing_ok=True)
            print(f"  ↩️  {parish}: {candidate} not a valid PDF, trying next date...")

        return FetchResult(url=rewritten, parish=parish, status="error",
                           error=last_err)

    # --- Load page ---
    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    )
    try:
        page = await context.new_page()
        main_response = None
        try:
            main_response = await page.goto(
                url, timeout=PAGE_LOAD_TIMEOUT_MS, wait_until="networkidle"
            )
        except PlaywrightTimeout:
            pass

        page_url = page.url

        # Detect Wix from response headers / page source
        site_type: Optional[str] = hint_site_type
        if not site_type and await _is_wix_page(page, main_response):
            site_type = "wix"

        # Fast-path: if history says this is an HTML-bulletin site, try that first
        if fast_html_path:
            bulletin_link = await _find_bulletin_image_link(page, page_url)
            if bulletin_link:
                print(f"  ⚡ Fast-path HTML bulletin for {parish}: {bulletin_link}")
                html_pdf = await _scrape_html_to_pdf(
                    bulletin_link, parish, output_dir, browser, context, site_type,
                    target=target,
                )
                if html_pdf and is_valid_pdf(html_pdf):
                    return FetchResult(
                        url=url, parish=parish, status="ok",
                        file_path=html_pdf, file_type="html_to_pdf",
                        site_type=site_type, source_url=bulletin_link,
                    )

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

        # Collect <embed src> and <object data> attributes (PDF viewers)
        try:
            embeds = await page.eval_on_selector_all(
                "embed[src]", "els => els.map(el => [el.src, ''])"
            )
            objects = await page.eval_on_selector_all(
                "object[data]", "els => els.map(el => [el.data, ''])"
            )
        except Exception:
            embeds, objects = [], []

        links: list[tuple[str, str]] = []
        for href, text in anchors:
            if not href:
                continue
            abs_href = urljoin(page_url, href)
            if ".pdf" in abs_href.lower() or any(
                kw in text.lower() for kw in BULLETIN_KEYWORDS
            ):
                links.append((abs_href, text))

        for src, _ in iframes:
            if not src:
                continue
            abs_src = urljoin(page_url, src)
            # Google Docs Viewer bypass: extract the real PDF URL from the viewer
            if "docs.google.com/viewer" in abs_src:
                qs = parse_qs(urlparse(abs_src).query)
                extracted_urls = qs.get("url", [])
                if extracted_urls and extracted_urls[0].startswith("http"):
                    links.append((extracted_urls[0], "google-docs-viewer"))
                continue
            if ".pdf" in abs_src.lower() or any(
                kw in abs_src.lower() for kw in BULLETIN_KEYWORDS
            ):
                links.append((abs_src, "iframe"))

        for src, _ in embeds + objects:
            if not src:
                continue
            abs_src = urljoin(page_url, src)
            if ".pdf" in abs_src.lower():
                links.append((abs_src, "embed/object"))

        top_pdfs = _pick_top_pdfs(links, target)
        best_pdf = top_pdfs[0] if top_pdfs else None

        # --- Sub-page crawling when no direct PDF found ---
        if not top_pdfs:
            sub_page_links: list[tuple[str, str]] = []
            for href, text in anchors:
                if not href:
                    continue
                text_lower = text.lower()
                if any(kw in text_lower for kw in SUB_PAGE_KEYWORDS):
                    abs_href = urljoin(page_url, href)
                    if abs_href.startswith("http") and abs_href != page_url:
                        sub_page_links.append((abs_href, text))

            for sub_url, sub_text in sub_page_links[:3]:
                sub_page = None
                try:
                    sub_page = await context.new_page()
                    sub_response = None
                    try:
                        sub_response = await sub_page.goto(
                            sub_url, timeout=PAGE_LOAD_TIMEOUT_MS, wait_until="networkidle"
                        )
                    except PlaywrightTimeout:
                        pass

                    content_type = ""
                    if sub_response:
                        content_type = sub_response.headers.get("content-type", "")
                    final_sub_url = sub_page.url
                    if content_type.startswith("application/pdf") or _url_ends_in_pdf(final_sub_url):
                        dest = output_dir / safe_filename(parish, ".pdf")
                        await _download_pdf(final_sub_url, dest, browser)
                        if _is_real_pdf(dest, parish, final_sub_url):
                            print(f"  🔍 Found PDF via sub-page for {parish}: {final_sub_url}")
                            best_pdf = final_sub_url
                            top_pdfs = [final_sub_url]
                            break
                        else:
                            dest.unlink(missing_ok=True)
                        continue

                    sub_anchors = await sub_page.eval_on_selector_all(
                        "a[href]",
                        "els => els.map(el => [el.href, el.innerText.trim()])",
                    )
                    sub_links: list[tuple[str, str]] = []
                    sub_page_url = sub_page.url
                    for sh, st in sub_anchors:
                        if not sh:
                            continue
                        abs_sh = urljoin(sub_page_url, sh)
                        if ".pdf" in abs_sh.lower() or any(
                            kw in st.lower() for kw in BULLETIN_KEYWORDS
                        ):
                            sub_links.append((abs_sh, st))

                    sub_top = _pick_top_pdfs(sub_links, target)
                    if sub_top:
                        print(f"  🔍 Found PDF(s) via sub-page for {parish}: {sub_top[0]}")
                        top_pdfs = sub_top
                        best_pdf = sub_top[0]
                        break
                except Exception as sub_exc:
                    print(f"  ⚠️  Sub-page error for {parish} ({sub_url}): {sub_exc}")
                finally:
                    if sub_page is not None:
                        try:
                            await sub_page.close()
                        except Exception:
                            pass

        # --- Try each PDF candidate in ranked order ---
        # Attempt download + validation for all top candidates before giving up.
        # Tiny files (< 50 KB) and invalid PDFs are skipped so we always try
        # the next-best link rather than returning an error immediately.
        html_fallback_url: Optional[str] = None  # first candidate that returned HTML instead of a PDF

        for pdf_candidate in top_pdfs:
            dest = output_dir / safe_filename(parish, ".pdf")
            try:
                await _download_pdf(pdf_candidate, dest, browser)
            except RuntimeError as exc:
                if "returned HTML" in str(exc):
                    dest.unlink(missing_ok=True)
                    if html_fallback_url is None:
                        html_fallback_url = pdf_candidate
                    print(
                        f"  ⚠️  {parish}: {pdf_candidate} returned HTML — "
                        f"trying next PDF candidate"
                    )
                else:
                    dest.unlink(missing_ok=True)
                    print(f"  ↩️  {parish}: {pdf_candidate} download error: {exc}")
                continue
            except Exception as exc:
                dest.unlink(missing_ok=True)
                print(f"  ↩️  {parish}: {pdf_candidate} download error: {exc}")
                continue

            if _is_real_pdf(dest, parish, pdf_candidate):
                return FetchResult(
                    url=url, parish=parish, status="ok",
                    file_path=dest, file_type="pdf",
                    candidate_urls=[h for h, _ in links],
                    site_type=site_type,
                    source_url=pdf_candidate,
                )
            dest.unlink(missing_ok=True)
            print(
                f"  ↩️  {parish}: {pdf_candidate} is not a valid/sufficient PDF "
                f"(< 50 KB or corrupt), trying next candidate..."
            )

        # All PDF candidates exhausted — update best_pdf for the HTML fallback path
        if html_fallback_url:
            best_pdf = html_fallback_url
        elif not top_pdfs:
            best_pdf = None  # no candidates were found

        # --- HTML bulletin fallback ---
        # When no PDF is found anywhere, look for a bulletin image/text link
        # pointing to an HTML page and scrape+convert it.
        bulletin_link = await _find_bulletin_image_link(page, page_url)
        # Also consider the HTML-returning link found above as a candidate
        if not bulletin_link and best_pdf:
            bulletin_link = best_pdf
        if bulletin_link:
            print(f"  🌐 Trying HTML bulletin fallback for {parish}: {bulletin_link}")
            base_domain = urlparse(page_url).netloc
            # First: look for a dated bulletin link within the landing page.
            # Handles listing pages (e.g. /latest-news) that link to dated bulletin pages.
            dated_link = await _find_dated_bulletin_link(
                bulletin_link, target, context, base_domain
            )
            if dated_link:
                print(f"  📅 Found dated bulletin link for {parish}: {dated_link}")
                html_pdf = await _scrape_html_to_pdf(
                    dated_link, parish, output_dir, browser, context, site_type,
                    target=target,
                )
                if html_pdf and is_valid_pdf(html_pdf):
                    return FetchResult(
                        url=url, parish=parish, status="ok",
                        file_path=html_pdf, file_type="html_to_pdf",
                        candidate_urls=[h for h, _ in links],
                        site_type=site_type,
                        source_url=dated_link,
                    )
            # Fallback: scrape the bulletin landing page directly
            html_pdf = await _scrape_html_to_pdf(
                bulletin_link, parish, output_dir, browser, context, site_type,
                target=target,
            )
            if html_pdf and is_valid_pdf(html_pdf):
                return FetchResult(
                    url=url, parish=parish, status="ok",
                    file_path=html_pdf, file_type="html_to_pdf",
                    candidate_urls=[h for h, _ in links],
                    site_type=site_type,
                    source_url=bulletin_link,
                )

        # --- Nothing found ---
        return FetchResult(
            url=url, parish=parish, status="error",
            error="No PDF found",
            candidate_urls=[h for h, _ in links],
            site_type=site_type,
        )

    finally:
        await context.close()


# ---------------------------------------------------------------------------
# Batch runner
# ---------------------------------------------------------------------------

async def fetch_all(
    urls: list[str],
    output_dir: Path,
    target: date,
    hints: Optional[dict[str, dict]] = None,
) -> list[FetchResult]:
    """Fetch all parishes concurrently, bounded by CONCURRENCY.

    *hints* maps ``parish_name_from_url(url)`` → hint dict from
    ``profiles.get_hint()``.  Pass ``None`` to disable profile-guided hints.
    """
    sem = asyncio.Semaphore(CONCURRENCY)
    hints = hints or {}

    async def _bounded(url: str, browser: Browser) -> FetchResult:
        parish_key = parish_name_from_url(url)
        hint = hints.get(parish_key)
        async with sem:
            return await fetch_parish(url, output_dir, target, browser, hint=hint)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        tasks = [_bounded(url, browser) for url in urls]
        results = list(await asyncio.gather(*tasks, return_exceptions=True))

        await asyncio.sleep(_PLAYWRIGHT_SHUTDOWN_DELAY_S)

        try:
            await browser.close()
        except Exception:
            pass

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
