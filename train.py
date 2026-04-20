from __future__ import annotations

import argparse
import asyncio
import json
import re
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
    print("Step 3: When the PDF opens or downloads, press ENTER here\n")
    print("Opening browser...")

    start_url = entry.bulletin_page or entry.example_url
    click_steps: list[dict[str, Any]] = []
    nav_urls: list[str] = []
    final_document_url: str | None = None

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        context = await browser.new_context(accept_downloads=True)
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

        await page.expose_binding("ph_record_click", handle_record_click)
        await page.add_init_script(
            """
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
        )

        page.on("framenavigated", handle_navigate)
        page.on("download", handle_download)

        try:
            await page.goto(start_url, wait_until="domcontentloaded", timeout=20_000)
        except Exception:
            print("⚠️ Could not open start URL automatically. Please navigate manually.")

        stop_event = asyncio.Event()
        page.on("close", lambda: stop_event.set())
        context.on("close", lambda: stop_event.set())
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

        if enter_task in done and browser.is_connected():
            await context.close()
            await browser.close()

    steps: list[dict[str, Any]] = [{"action": "goto", "url": start_url}]
    steps.extend(click_steps)

    if not final_document_url and nav_urls:
        for url in reversed(nav_urls):
            lowered = url.lower()
            if lowered.endswith(".pdf") or lowered.endswith(".docx"):
                final_document_url = url
                break

    if final_document_url:
        lower = final_document_url.lower()
        pattern = "*.docx" if lower.endswith(".docx") else "*.pdf"
        steps.append({"action": "download", "url_pattern": pattern, "captured_url": final_document_url})
    else:
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
