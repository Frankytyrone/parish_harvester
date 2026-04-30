from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import tempfile
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from playwright.async_api import async_playwright

from harvester.config import PARISHES_DIR
from harvester.fetcher import ParishEntry, parse_evidence_file

_MONTH_RE = re.compile(
    r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?)\b",
    re.IGNORECASE,
)

_CLICK_TRACKER_JS = """
(() => {
  const cssPath = (el) => {
    if (!el || el.nodeType !== Node.ELEMENT_NODE) return '';
    const parts = [];
    let current = el;
    while (current && current.nodeType === Node.ELEMENT_NODE && parts.length < 6) {
      let selector = current.tagName.toLowerCase();
      if (current.id) {
        selector += '#' + current.id;
        parts.unshift(selector);
        break;
      }
      const parent = current.parentElement;
      if (parent) {
        const siblings = Array.from(parent.children).filter(c => c.tagName === current.tagName);
        if (siblings.length > 1) {
          selector += `:nth-of-type(${siblings.indexOf(current) + 1})`;
        }
      }
      parts.unshift(selector);
      current = current.parentElement;
    }
    return parts.join(' > ');
  };

  document.addEventListener('click', (event) => {
    const target = event.target instanceof Element
      ? event.target.closest('a,button,[role],input[type="submit"],input[type="button"]')
      : null;
    if (!target) return;
    window.ph_record_click({
      tag: (target.tagName || '').toLowerCase(),
      role: (target.getAttribute('role') || '').toLowerCase(),
      text: (target.innerText || target.textContent || '').trim().slice(0, 200),
      href: target.getAttribute('href') || '',
      css_path: cssPath(target),
    });
  }, true);
})();
"""


@dataclass
class TrainingTarget:
    diocese: str
    entry: ParishEntry


def _normalize_parish_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.casefold().replace("&", " and ")
    normalized = re.sub(r"[’'`]", "", normalized)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return " ".join(normalized.split())


def _remove_parenthetical_text(text: str) -> str:
    result: list[str] = []
    depth = 0
    for ch in text:
        if ch == "(":
            depth += 1
            continue
        if ch == ")":
            if depth > 0:
                depth -= 1
                continue
        if depth == 0:
            result.append(ch)
    return "".join(result)


def _parish_name_forms(name: str) -> set[str]:
    forms: set[str] = set()
    base = _normalize_parish_text(name)
    if base:
        forms.add(base)
    without_parens = _remove_parenthetical_text(name)
    no_paren_form = _normalize_parish_text(without_parens)
    if no_paren_form:
        forms.add(no_paren_form)

    expanded: set[str] = set()
    for form in forms:
        expanded.add(form)
        expanded.add(re.sub(r"\bst\b", "saint", form))
        expanded.add(re.sub(r"\bsaint\b", "st", form))
    return {f for f in expanded if f}


def _discover_dioceses(parishes_dir: Path) -> list[str]:
    names: list[str] = []
    for path in sorted(parishes_dir.glob("*_bulletin_urls.txt")):
        names.append(path.stem.replace("_bulletin_urls", ""))
    return names


def _date_agnostic_token(text: str) -> str:
    cleaned = " ".join(text.split())
    if not cleaned:
        return ""

    lowered = cleaned.lower()
    for keyword in ("bulletin", "newsletter", "download", "weekly", "parish"):
        if keyword in lowered:
            return keyword.title()

    stripped = _MONTH_RE.sub(" ", cleaned)
    stripped = re.sub(r"\b\d{1,4}(?:st|nd|rd|th)?\b", " ", stripped, flags=re.IGNORECASE)
    words = [w for w in re.split(r"[^a-zA-Z]+", stripped) if len(w) >= 3]
    if not words:
        words = [w for w in re.split(r"[^a-zA-Z]+", cleaned) if len(w) >= 3]
    return words[0] if words else ""


def _escape_selector_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("'", "\\'")


def _href_hint_selector(href: str) -> str | None:
    if not href:
        return None
    path = unquote(urlparse(href).path or "").lower()
    ext = ".docx" if path.endswith(".docx") else ".pdf"
    stem = Path(path).stem
    stem = _MONTH_RE.sub(" ", stem)
    stem = re.sub(r"\b\d{1,4}(?:st|nd|rd|th)?\b", " ", stem, flags=re.IGNORECASE)
    words = [w for w in re.split(r"[^a-z]+", stem) if len(w) >= 4]
    preferred = None
    for candidate in words:
        if candidate in {"bulletin", "newsletter", "weekly", "parish"}:
            preferred = candidate
            break
    if preferred is None and words:
        preferred = words[0]
    if preferred:
        return f"a[href*='{preferred}'][href$='{ext}']"
    return None


def _build_click_step(payload: dict[str, Any]) -> dict[str, Any] | None:
    tag = (payload.get("tag") or "").lower()
    role = (payload.get("role") or "").lower()
    text = (payload.get("text") or "").strip()
    href = (payload.get("href") or "").strip()
    css_path = (payload.get("css_path") or "").strip()

    token = _date_agnostic_token(text)
    if not token and not href and not css_path:
        return None

    token_sel = _escape_selector_text(token) if token else ""
    if tag == "a" and token_sel:
        primary = f"a:has-text('{token_sel}')"
    elif token_sel:
        primary = f":has-text('{token_sel}')"
    elif href:
        primary = "a[href$='.pdf']" if ".pdf" in href.lower() else "a[href$='.docx']"
    else:
        primary = css_path

    fallbacks: list[str] = []
    if role and token_sel:
        fallbacks.append(f'role={role}[name="{token}"]')
    href_hint = _href_hint_selector(href)
    if href_hint:
        fallbacks.append(href_hint)
    if href.lower().endswith(".docx"):
        fallbacks.append("a[href$='.docx']")
    else:
        fallbacks.append("a[href$='.pdf']")
    fallbacks.append("a[href*='.pdf']")
    if css_path:
        fallbacks.append(css_path)

    deduped: list[str] = []
    for sel in fallbacks:
        if sel and sel != primary and sel not in deduped:
            deduped.append(sel)

    step = {"action": "click", "selector": primary}
    if deduped:
        step["fallback_selectors"] = deduped
    return step


def _normalize_http_url(url: str) -> str:
    cleaned = (url or "").strip()
    if not cleaned:
        return ""
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"}:
        return ""
    return cleaned


def _build_mark_step(action: str, url: str) -> dict[str, Any] | None:
    normalized = _normalize_http_url(url)
    if not normalized:
        return None
    if action not in {"image", "html"}:
        return None
    return {"action": action, "url": normalized}


def _extract_int(payload: dict[str, Any], keys: tuple[str, ...], default: int = 0) -> int:
    """Return the first payload value from *keys* that can be coerced to int."""
    for key in keys:
        value = payload.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
    return default


def _has_trainer_extension(extension_dir: Path) -> bool:
    required = {"manifest.json", "content.js", "background.js"}
    return extension_dir.is_dir() and all((extension_dir / name).is_file() for name in required)


_DEAD_URL_NAV_ERRORS = (
    "err_name_not_resolved",
    "err_connection_refused",
    "err_connection_timed_out",
    "err_address_unreachable",
    "net::err",
    "timeout",
    "name or service not known",
)

_CHROME_ERROR_TITLES = (
    "err_name_not_resolved",
    "err_connection_refused",
    "err_connection_timed_out",
    "err_address_unreachable",
    "this site can't be reached",
    "this webpage is not available",
)

_DEAD_URL_PROMPT = "   Press D then Enter to mark as dead and skip, or just Enter to try anyway: "

# Harvester should skip parishes whose recipe contains "status": "dead_url"
def _write_dead_recipe(recipe_path: Path, entry: "ParishEntry", start_url: str) -> None:
    """Write a recipe file that marks this parish URL as dead/unreachable."""
    recipe = {
        "parish": entry.display_name,
        "url": start_url,
        "status": "dead_url",
        "dead_reason": "URL unreachable during training — DNS failure, connection refused, or timeout.",
    }
    recipe_path.parent.mkdir(parents=True, exist_ok=True)
    recipe_path.write_text(json.dumps(recipe, indent=2, ensure_ascii=False), encoding="utf-8")


def _match_parish(parish_query: str, diocese: str | None, parishes_dir: Path) -> TrainingTarget:
    query = parish_query.strip()
    if not query:
        raise ValueError("Parish name cannot be empty")
    query_forms = _parish_name_forms(query)

    dioceses = [diocese] if diocese else _discover_dioceses(parishes_dir)
    matches: list[TrainingTarget] = []
    known_parishes: dict[str, set[str]] = {}

    for d in dioceses:
        if not d:
            continue
        try:
            entries = parse_evidence_file(d, parishes_dir)
        except FileNotFoundError:
            continue
        known_parishes[d] = {entry.display_name for entry in entries}
        for entry in entries:
            entry_forms = _parish_name_forms(entry.display_name)
            if query_forms & entry_forms:
                matches.append(TrainingTarget(diocese=d, entry=entry))
                continue
            if any(
                qf in ef or ef in qf
                for qf in query_forms
                for ef in entry_forms
                if qf and ef
            ):
                matches.append(TrainingTarget(diocese=d, entry=entry))

    if not matches:
        detected = sorted(
            {(d, name) for d, names in known_parishes.items() for name in names},
            key=lambda item: (item[1].lower(), item[0]),
        )
        if detected:
            options = "\n".join(f"  - {name} ({d})" for d, name in detected)
            raise ValueError(
                f'No parish matched "{parish_query}". Detected parishes:\n{options}'
            )
        raise ValueError(f'No parish matched "{parish_query}"')

    exact = [m for m in matches if query_forms & _parish_name_forms(m.entry.display_name)]
    if len(exact) == 1:
        return exact[0]

    unique: dict[tuple[str, str], TrainingTarget] = {
        (m.diocese, m.entry.display_name): m for m in matches
    }
    if len(unique) == 1:
        return next(iter(unique.values()))

    sorted_matches = sorted(
        unique.values(),
        key=lambda m: (m.entry.display_name.lower(), m.diocese),
    )
    options = "\n".join(
        f"  - {m.entry.display_name} ({m.diocese})" for m in sorted_matches
    )
    raise ValueError(
        f'Parish query "{parish_query}" is ambiguous. Please be more specific:\n{options}'
    )


async def run_training(parish_query: str, diocese: str | None, parishes_dir: Path = PARISHES_DIR) -> Path:
    target = _match_parish(parish_query, diocese, parishes_dir)
    entry = target.entry
    recipes_dir = parishes_dir / "recipes"
    recipes_dir.mkdir(parents=True, exist_ok=True)
    recipe_path = recipes_dir / f"{entry.key}.json"

    print(f"🎯 Matched parish: {entry.display_name} ({target.diocese})")
    print(f"🎬 Training mode for: {entry.display_name}")
    print("===================================")
    print("A browser window will open.\n")
    print("Step 1: Navigate to the parish bulletin page")
    print("Step 2: Click through to find the PDF bulletin")
    print("Step 3: Use the extension floating toolbar or context menu to mark image/HTML/file bulletins if needed")
    print("Step 4: When done, press ENTER here\n")
    print("Opening browser...")

    start_url = entry.bulletin_page or entry.example_url
    click_steps: list[dict[str, Any]] = []
    nav_urls: list[str] = []
    final_document_url: str | None = None
    marked_step: dict[str, Any] | None = None
    crop_step: dict[str, Any] | None = None

    extension_dir = Path(__file__).resolve().parent / "extension"
    use_extension = _has_trainer_extension(extension_dir)
    user_data_dir: str | None = None

    try:
        async with async_playwright() as pw:
            browser = None
            if use_extension:
                user_data_dir = tempfile.mkdtemp(
                    prefix="parish-trainer-profile-",
                    dir=tempfile.gettempdir(),
                )
                try:
                    os.chmod(user_data_dir, 0o700)
                except OSError:
                    pass
                context = await pw.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    headless=False,
                    accept_downloads=True,
                    no_viewport=True,
                    args=[
                        f"--disable-extensions-except={extension_dir}",
                        f"--load-extension={extension_dir}",
                        "--start-maximized",
                        "--window-size=1400,900",
                    ],
                )
                page = context.pages[0] if context.pages else await context.new_page()
            else:
                browser = await pw.chromium.launch(
                    headless=False,
                    args=["--start-maximized", "--window-size=1400,900"],
                )
                context = await browser.new_context(accept_downloads=True, no_viewport=True)
                page = await context.new_page()

            def handle_navigate(frame) -> None:
                nonlocal final_document_url
                if frame != page.main_frame:
                    return
                url = frame.url
                if not url.startswith("http"):
                    return
                nav_urls.append(url)
                lowered = url.lower()
                if lowered.endswith(".pdf") or lowered.endswith(".docx"):
                    final_document_url = url

            async def handle_download(download) -> None:
                nonlocal final_document_url
                try:
                    final_document_url = download.url
                except Exception:
                    pass

            async def handle_record_click(_source, payload: dict[str, Any]) -> None:
                step = _build_click_step(payload)
                if not step:
                    return
                if click_steps and click_steps[-1].get("selector") == step.get("selector"):
                    return
                click_steps.append(step)

            async def handle_mark_image(_source, payload: dict[str, Any]) -> None:
                nonlocal marked_step
                step = _build_mark_step("image", str(payload.get("url", "")))
                if not step:
                    return
                marked_step = step
                print(f"\n🖼️ Marked bulletin image: {step['url']}")

            async def handle_mark_html(_source, payload: dict[str, Any]) -> None:
                nonlocal marked_step
                step = _build_mark_step("html", str(payload.get("url", "")))
                if not step:
                    return
                marked_step = step
                print(f"\n🔗 Marked bulletin HTML page: {step['url']}")

            async def handle_mark_download_url(_source, payload: dict[str, Any]) -> None:
                nonlocal final_document_url, marked_step
                if payload.get("url") == "dead_url" or payload.get("type") == "dead_url":
                    _write_dead_recipe(recipe_path, entry, start_url)
                    final_document_url = "dead_url"
                    print(f"\n🔴 Parish marked as dead URL via toolbar button.")
                    return
                if payload.get("url") == "no_bulletin":
                    final_document_url = "no_bulletin"
                    print("🚫 Parish marked as having no bulletin — skipping.")
                    return
                url = _normalize_http_url(str(payload.get("url", "")))
                if not url:
                    return
                lowered = url.lower()
                if lowered.endswith((".jpg", ".jpeg", ".png", ".webp")):
                    step = _build_mark_step("image", url)
                    if step:
                        marked_step = step
                        print(f"\n🖼️ Marked bulletin image: {step['url']}")
                    return
                final_document_url = url
                marked_step = None
                print(f"\n📄 Marked bulletin file URL: {url}")

            async def handle_mark_crop(_source, payload: dict) -> None:
                nonlocal crop_step, marked_step, final_document_url
                raw_sections = payload.get("sections")
                crop_step = {
                    "action": "crop_screenshot",
                    "x": _extract_int(payload, ("x",)),
                    "y": _extract_int(payload, ("y",)),
                    "width": _extract_int(payload, ("width",)),
                    "height": _extract_int(payload, ("height",)),
                    "page_x": _extract_int(payload, ("pageX", "page_x", "x")),
                    "page_y": _extract_int(payload, ("pageY", "page_y", "y")),
                    "element_selector": str(payload.get("element_selector", "") or ""),
                }
                if isinstance(raw_sections, list) and raw_sections:
                    crop_step["sections"] = [
                        {
                            "x": _extract_int(s, ("x",)),
                            "y": _extract_int(s, ("y",)),
                            "width": _extract_int(s, ("width",)),
                            "height": _extract_int(s, ("height",)),
                            "page_x": _extract_int(s, ("pageX", "page_x", "x")),
                            "page_y": _extract_int(s, ("pageY", "page_y", "y")),
                        }
                        for s in raw_sections
                        if isinstance(s, dict)
                    ]
                marked_step = None
                final_document_url = None
                if crop_step.get("sections"):
                    print(
                        f"\n✂️ Multi-section crop recorded: {len(crop_step['sections'])} sections"
                    )
                else:
                    print(
                        f"\n✂️ Crop recorded: x={crop_step['x']}, y={crop_step['y']}, "
                        f"w={crop_step['width']}, h={crop_step['height']}"
                    )

            async def handle_undo_step(_source, payload: dict[str, Any]) -> None:
                """Remove the most-recently recorded step of the given type.

                Called by the extension's "Undo Last Step" button so the UI and
                the Python-side state stay in sync.
                """
                nonlocal marked_step, final_document_url, crop_step
                step_type = str(payload.get("step_type", ""))
                if step_type == "click" and click_steps:
                    removed = click_steps.pop()
                    print(f"\n↩ Undo: removed click step {removed.get('selector', '')!r}")
                elif step_type in ("mark_html", "mark_image") and marked_step:
                    print(f"\n↩ Undo: removed mark step ({marked_step.get('action', '')})")
                    marked_step = None
                elif step_type == "mark_file":
                    if final_document_url:
                        print(f"\n↩ Undo: removed file URL {final_document_url!r}")
                        final_document_url = None
                elif step_type == "crop":
                    if crop_step:
                        print("\n↩ Undo: removed crop step")
                        crop_step = None
                else:
                    print(f"\n↩ Undo requested for step_type={step_type!r} — nothing to remove")

            await page.expose_binding("ph_record_click", handle_record_click)
            await page.expose_binding("ph_mark_image", handle_mark_image)
            await page.expose_binding("ph_mark_html", handle_mark_html)
            await page.expose_binding("ph_mark_download_url", handle_mark_download_url)
            await page.expose_binding("ph_mark_crop", handle_mark_crop)
            await page.expose_binding("ph_undo_step", handle_undo_step)
            if not use_extension:
                await page.add_init_script(_CLICK_TRACKER_JS)

                async def _reinject_click_tracker() -> None:
                    try:
                        await asyncio.sleep(0.6)
                        await page.evaluate(_CLICK_TRACKER_JS)
                    except Exception:
                        pass

                page.on("load", lambda: asyncio.ensure_future(_reinject_click_tracker()))

            page.on("framenavigated", handle_navigate)
            page.on("download", handle_download)

            try:
                try:
                    await page.goto(start_url, wait_until="domcontentloaded", timeout=20_000)
                except Exception as nav_err:
                    err_str = str(nav_err).lower()
                    is_dead = any(k in err_str for k in _DEAD_URL_NAV_ERRORS)
                    if is_dead:
                        print(f"\n🔴 Dead URL detected: {start_url}")
                        print("   The website is unreachable (DNS failure, connection refused, or timeout).")
                        answer = await asyncio.to_thread(input, _DEAD_URL_PROMPT)
                        if answer.strip().lower() == "d":
                            _write_dead_recipe(recipe_path, entry, start_url)
                            print(f"✅ Marked as dead. Skipping {entry.display_name}.")
                            return recipe_path
                    else:
                        raise

                # Detect Chrome net-error pages even when goto() doesn't raise
                page_title = await page.title()
                page_url = page.url
                if any(t in page_title.lower() for t in _CHROME_ERROR_TITLES) or page_url.startswith("chrome-error://"):
                    print(f"\n🔴 Dead URL detected: {start_url}")
                    print("   Chrome reports this website is unreachable.")
                    answer = await asyncio.to_thread(input, _DEAD_URL_PROMPT)
                    if answer.strip().lower() == "d":
                        _write_dead_recipe(recipe_path, entry, start_url)
                        print(f"✅ Marked as dead. Skipping {entry.display_name}.")
                        return recipe_path

                if use_extension:
                    await asyncio.sleep(0.3)
                    try:
                        await page.evaluate(
                            "window.postMessage("
                            "{direction: 'from-isolated', message: {type: 'toggle_toolbar'}}, '*'"
                            ")"
                        )
                        print("✅ Parish Trainer toolbar ready")
                    except Exception:
                        print(
                            "⚠️  Could not auto-show toolbar. "
                            "Click the Parish Trainer icon in the Chrome toolbar to show it."
                        )
                if not use_extension:
                    await asyncio.sleep(0.8)
                    try:
                        await page.evaluate(_CLICK_TRACKER_JS)
                    except Exception:
                        pass
            except Exception:
                print("⚠️ Could not open start URL automatically. Please navigate manually.")

            stop_event = asyncio.Event()
            page.on("close", lambda: stop_event.set())
            context.on("close", lambda: stop_event.set())
            if browser is not None:
                browser.on("disconnected", lambda: stop_event.set())

            print()
            enter_task = asyncio.create_task(
                asyncio.to_thread(input, "✅ When you are done, press ENTER here... ")
            )
            wait_task = asyncio.create_task(stop_event.wait())

            done, pending = await asyncio.wait(
                {enter_task, wait_task}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()

            if enter_task in done and (browser is None or browser.is_connected()):
                await context.close()
                if browser is not None:
                    await browser.close()
    finally:
        if user_data_dir:
            try:
                shutil.rmtree(user_data_dir)
            except OSError as exc:
                print(
                    "⚠️ Could not remove temporary browser profile "
                    f"{user_data_dir}; sensitive browsing data may remain: {exc}"
                )

    steps: list[dict[str, Any]] = [{"action": "goto", "url": start_url}]
    steps.extend(click_steps)

    if marked_step:
        steps.append(marked_step)
    if crop_step:
        steps.append(crop_step)
    elif not marked_step and not final_document_url and nav_urls:
        for url in reversed(nav_urls):
            lowered = url.lower()
            if lowered.endswith(".pdf") or lowered.endswith(".docx"):
                final_document_url = url
                break

    if not marked_step and not crop_step and final_document_url:
        lower = final_document_url.lower()
        pattern = "*.docx" if lower.endswith(".docx") else "*.pdf"
        steps.append({"action": "download", "url_pattern": pattern, "captured_url": final_document_url})
    elif not marked_step and not crop_step:
        steps.append({"action": "download", "url_pattern": "*.pdf"})

    recipe = {
        "parish_key": entry.key,
        "display_name": entry.display_name,
        "recorded_date": date.today().isoformat(),
        "start_url": start_url,
        "steps": steps,
    }

    recipe_path.write_text(json.dumps(recipe, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("\n✅ Recipe saved! Here's what was recorded:\n")
    for idx, step in enumerate(steps, start=1):
        action = step.get("action")
        if action == "goto":
            print(f"{idx}. Go to: {step.get('url', '')}")
        elif action == "click":
            print(f"{idx}. Click: {step.get('selector', '')}")
        elif action == "download":
            shown = step.get("captured_url") or step.get("url_pattern", "*.pdf")
            print(f"{idx}. Download: {shown}")
        elif action == "image":
            print(f"{idx}. Image: {step.get('url', '')}")
        elif action == "html":
            print(f"{idx}. HTML link: {step.get('url', '')}")
        elif action == "crop_screenshot":
            print(
                f"{idx}. Crop screenshot: x={step.get('x', 0)}, y={step.get('y', 0)}, "
                f"w={step.get('width', 0)}, h={step.get('height', 0)}"
            )

    print(f"\nSaved to: {recipe_path}")
    print("\nThis will be replayed automatically during harvests.")
    print(f'To re-train, run: python main.py --train "{entry.display_name}"')

    return recipe_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a parish bulletin replay recipe")
    parser.add_argument("parish_name", help="Parish display name (partial match allowed)")
    parser.add_argument(
        "--diocese",
        default=None,
        help="Optional diocese filter (e.g. derry_diocese)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        asyncio.run(run_training(args.parish_name, diocese=args.diocese, parishes_dir=PARISHES_DIR))
    except Exception as exc:
        print(f"💥 Training failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
