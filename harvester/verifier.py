"""
verifier.py — Stage 2: Verify bulletin currency using OpenAI GPT-4o Vision.
"""
from __future__ import annotations

import base64
import io
import re
from datetime import date
from pathlib import Path
from typing import Optional

from PIL import Image

from .config import GITHUB_TOKEN, GITHUB_MODELS_ENDPOINT, MODEL_NAME, is_fresh

# Lazy import so the rest of the app works without openai installed
try:
    from openai import OpenAI
    _openai_available = True
except ImportError:
    _openai_available = False


VERIFY_PROMPT = (
    "This is a parish bulletin. "
    "What date or week is this bulletin for? "
    "Reply with ONLY the date in YYYY-MM-DD format, "
    "or 'UNKNOWN' if you cannot determine it."
)

_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


# ---------------------------------------------------------------------------
# PDF → image conversion
# ---------------------------------------------------------------------------

def _pdf_first_page_to_image(pdf_path: Path) -> Image.Image:
    """Convert the first page of a PDF to a Pillow Image."""
    try:
        from pdf2image import convert_from_path
    except ImportError as exc:
        raise RuntimeError("pdf2image is required for PDF verification") from exc
    pages = convert_from_path(str(pdf_path), first_page=1, last_page=1, dpi=150)
    if not pages:
        raise RuntimeError(f"Could not render any pages from {pdf_path}")
    return pages[0]


def _image_to_base64(img: Image.Image) -> str:
    """Encode a Pillow Image to a base64 PNG string."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _load_image(file_path: Path) -> Image.Image:
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        return _pdf_first_page_to_image(file_path)
    else:
        return Image.open(file_path)


# ---------------------------------------------------------------------------
# OpenAI call
# ---------------------------------------------------------------------------

def _call_model(b64_image: str) -> str:
    """Call GPT-4o vision via GitHub Models API and return raw text response."""
    if not _openai_available:
        raise RuntimeError("openai-compatible client package is not installed")
    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN is not set")

    client = OpenAI(
        base_url=GITHUB_MODELS_ENDPOINT,
        api_key=GITHUB_TOKEN,
    )
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{b64_image}",
                            "detail": "low",
                        },
                    },
                    {"type": "text", "text": VERIFY_PROMPT},
                ],
            }
        ],
        max_tokens=20,
        temperature=0,
    )
    return response.choices[0].message.content.strip()


def _parse_date(text: str) -> Optional[date]:
    """Extract a YYYY-MM-DD date from the model's reply."""
    m = _ISO_DATE_RE.search(text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def verify_file(file_path: Path, target: date) -> str:
    """
    Verify a bulletin file against *target*.

    Returns one of: "FRESH", "STALE", "UNKNOWN", "ERROR"
    """
    try:
        img = _load_image(file_path)
        b64 = _image_to_base64(img)
        raw = _call_model(b64)

        if raw.upper() == "UNKNOWN" or not _ISO_DATE_RE.search(raw):
            return "UNKNOWN"

        bulletin_date = _parse_date(raw)
        if bulletin_date is None:
            return "UNKNOWN"

        return "FRESH" if is_fresh(bulletin_date, target) else "STALE"

    except Exception as exc:
        return f"ERROR: {exc}"
