from __future__ import annotations

import fnmatch
import json
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, unquote, urljoin, urlparse

from playwright.async_api import Browser, Page, TimeoutError as PlaywrightTimeoutError

from .config import PAGE_LOAD_TIMEOUT_MS, PARISHES_DIR


class RecipeReplayError(RuntimeError):
    """Raised when replaying a trained parish recipe fails."""


DOCX_CONVERSION_TIMEOUT_S = 60
RECIPE_STEP_TIMEOUT_MS = 15_000
POST_CLICK_WAIT_TIMEOUT_MS = 3_000
MAX_SELECTOR_ERRORS = 3


def recipe_path_for(parish_key: str, parishes_dir: Path = PARISHES_DIR) -> Path:
    return parishes_dir / "recipes" / f"{parish_key}.json"


def load_recipe(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RecipeReplayError(f"Recipe not found: {path}") from exc
    except Exception as exc:
        raise RecipeReplayError(f"Invalid recipe JSON: {path}") from exc

    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        raise RecipeReplayError("Recipe has no steps")
    return data


def _unwrap_docs_viewer_url(url: str) -> str:
    parsed = urlparse(url)
    if "docs.google.com" not in parsed.netloc.lower():
        return url
    if "viewer" not in parsed.path and "viewerng" not in parsed.path:
        return url
    raw = parse_qs(parsed.query).get("url", [""])[0].strip()
    return unquote(raw) if raw else url


def _is_document_url(url: str) -> bool:
    lower = _unwrap_docs_viewer_url(url).lower()
    path = urlparse(lower).path
    if path.endswith(".pdf") or path.endswith(".docx"):
        return True
    return "drive.google.com/file/d/" in lower or "docs.google.com/viewer" in lower


def _is_pdf_content(data: bytes) -> bool:
    return data[:4] == b"%PDF"


def _normalize_doc_url(url: str) -> str:
    url = _unwrap_docs_viewer_url(url)
    m = re.search(r"drive\.google\.com/file/d/([^/?#]+)", url)
    if m:
        file_id = m.group(1)
        return (
            "https://drive.usercontent.google.com/download"
            f"?id={file_id}&export=download"
        )
    return url


async def _convert_docx_to_pdf_bytes(docx_bytes: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        docx_path = tmp_path / "bulletin.docx"
        out_pdf = tmp_path / "bulletin.pdf"
        docx_path.write_bytes(docx_bytes)
        libreoffice_error = ""

        try:
            result = subprocess.run(
                [
                    "libreoffice",
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(tmp_path),
                    str(docx_path),
                ],
                capture_output=True,
                timeout=DOCX_CONVERSION_TIMEOUT_S,
            )
            if result.returncode == 0 and out_pdf.exists():
                return out_pdf.read_bytes()
            libreoffice_error = (result.stderr or b"").decode("utf-8", errors="ignore").strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        try:
            import docx as _docx  # type: ignore[import]
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib.units import cm
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
        except ImportError as exc:
            suffix = f" LibreOffice error: {libreoffice_error}" if libreoffice_error else ""
            raise RecipeReplayError(
                f"Could not convert DOCX to PDF (missing converter dependencies).{suffix}"
            ) from exc

        doc = _docx.Document(str(docx_path))
        lines = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
        if not lines:
            raise RecipeReplayError("DOCX has no text content")

        fallback_pdf = tmp_path / "fallback.pdf"
        styles = getSampleStyleSheet()
        pdf_doc = SimpleDocTemplate(
            str(fallback_pdf),
            pagesize=A4,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
            leftMargin=2.5 * cm,
            rightMargin=2.5 * cm,
        )
        story = []
        for line in lines:
            safe = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            story.append(Paragraph(safe, styles["Normal"]))
            story.append(Spacer(1, 0.15 * cm))
        pdf_doc.build(story)
        return fallback_pdf.read_bytes()


async def _save_download_to_pdf(download, dest: Path) -> str:
    suggested = (download.suggested_filename or "").lower()
    if suggested.endswith(".docx"):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_docx = Path(tmpdir) / "download.docx"
            await download.save_as(str(tmp_docx))
            pdf_bytes = await _convert_docx_to_pdf_bytes(tmp_docx.read_bytes())
            dest.write_bytes(pdf_bytes)
            return "docx_to_pdf"

    await download.save_as(str(dest))
    return "pdf"


async def _download_document_url(page: Page, raw_url: str, dest: Path) -> tuple[str, str]:
    url = _normalize_doc_url(raw_url)
    response = await page.request.get(url, timeout=PAGE_LOAD_TIMEOUT_MS)
    if not response.ok:
        raise RecipeReplayError(f"HTTP {response.status} for {raw_url}")

    body = await response.body()
    path = urlparse(url.lower()).path
    if path.endswith(".docx"):
        pdf_bytes = await _convert_docx_to_pdf_bytes(body)
        dest.write_bytes(pdf_bytes)
        return raw_url, "docx_to_pdf"

    if _is_pdf_content(body):
        dest.write_bytes(body)
        return raw_url, "pdf"

    content_type = response.headers.get("content-type", "")
    if "text/html" in content_type:
        raise RecipeReplayError(f"Server returned HTML instead of document for {raw_url}")

    dest.write_bytes(body)
    return raw_url, "pdf"


async def _replay_click(page: Page, step: dict) -> None:
    selectors: list[str] = []
    selector = (step.get("selector") or "").strip()
    if selector:
        selectors.append(selector)
    selectors.extend(
        s.strip() for s in step.get("fallback_selectors", []) if isinstance(s, str) and s.strip()
    )

    if not selectors:
        raise RecipeReplayError("Recipe click step missing selector")

    errors: list[str] = []
    for sel in selectors:
        try:
            locator = page.locator(sel).first
            await locator.wait_for(state="visible", timeout=RECIPE_STEP_TIMEOUT_MS)
            await locator.click(timeout=RECIPE_STEP_TIMEOUT_MS)
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=POST_CLICK_WAIT_TIMEOUT_MS)
            except PlaywrightTimeoutError:
                pass
            return
        except Exception as exc:
            errors.append(f"{sel}: {exc}")

    detail = "; ".join(errors[:MAX_SELECTOR_ERRORS]) if errors else "no selector details available"
    raise RecipeReplayError(
        f"Recipe outdated — re-train with --train (all selectors failed: {detail})"
    )


async def replay_recipe(
    recipe_path: Path,
    dest: Path,
    browser: Browser,
) -> tuple[Path, str, str]:
    recipe = load_recipe(recipe_path)
    steps = recipe["steps"]

    context = await browser.new_context(accept_downloads=True)
    page = await context.new_page()
    downloads: list = []
    page.on("download", lambda d: downloads.append(d))

    try:
        for step in steps:
            action = step.get("action")
            if action == "goto":
                url = (step.get("url") or "").strip()
                if not url:
                    raise RecipeReplayError("Recipe goto step missing URL")
                await page.goto(url, timeout=RECIPE_STEP_TIMEOUT_MS, wait_until="domcontentloaded")
                continue

            if action == "click":
                await _replay_click(page, step)
                if downloads:
                    file_type = await _save_download_to_pdf(downloads.pop(0), dest)
                    source_url = page.url
                    return dest, file_type, source_url
                if _is_document_url(page.url):
                    source_url, file_type = await _download_document_url(page, page.url, dest)
                    return dest, file_type, source_url
                continue

            if action == "download":
                if downloads:
                    file_type = await _save_download_to_pdf(downloads.pop(0), dest)
                    source_url = page.url
                    return dest, file_type, source_url

                if _is_document_url(page.url):
                    source_url, file_type = await _download_document_url(page, page.url, dest)
                    return dest, file_type, source_url

                pattern = (step.get("url_pattern") or "*.pdf").strip() or "*.pdf"
                links = await page.eval_on_selector_all(
                    "a[href],iframe[src],embed[src],object[data]",
                    """
                    (els) => els.map(el => el.getAttribute('href') || el.getAttribute('src') || el.getAttribute('data') || '').filter(Boolean)
                    """,
                )
                last_err = ""
                for raw in links:
                    if not isinstance(raw, str):
                        continue
                    resolved = urljoin(page.url, raw)
                    lower = resolved.lower()
                    if fnmatch.fnmatch(lower, pattern.lower()) or (
                        pattern == "*.pdf" and ".pdf" in lower
                    ) or (pattern == "*.docx" and ".docx" in lower):
                        try:
                            source_url, file_type = await _download_document_url(page, resolved, dest)
                            return dest, file_type, source_url
                        except RecipeReplayError as exc:
                            last_err = str(exc)
                            continue

                if last_err:
                    raise RecipeReplayError(last_err)
                raise RecipeReplayError("Recipe download step did not find a matching document URL")

            raise RecipeReplayError(f"Unsupported recipe action: {action}")

        if downloads:
            file_type = await _save_download_to_pdf(downloads.pop(0), dest)
            return dest, file_type, page.url
        if _is_document_url(page.url):
            source_url, file_type = await _download_document_url(page, page.url, dest)
            return dest, file_type, source_url

        raise RecipeReplayError("Recipe finished without downloading a document")
    finally:
        try:
            await context.close()
        except Exception:
            pass
