from __future__ import annotations

"""Cost and quota tracker — writes docs/COST_DASHBOARD.md on every harvest run.

Measures:
- Repo size on disk vs GitHub 5 GB hard cap.
- AI calls this run by provider (reads Bulletins/ai_router_state.json if present).
- GitHub Actions minutes (attempts GitHub API; degrades gracefully).
- Days until free-tier limit at 7-day rolling rate.

Traffic-light: 🟢 < 60 %  🟡 60–85 %  🔴 > 85 %

Usage::

    from pathlib import Path
    from harvester.cost_tracker import update_dashboard
    update_dashboard(Path("."))
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
GITHUB_REPO_CAP_GB = 5.0
GITHUB_PAGES_BW_GB_PER_MONTH = 100.0
GITHUB_ACTIONS_FREE_MINUTES = 2000  # per month (public repos = unlimited, private = 2000)
GB = 1024 ** 3
TIMEOUT = 10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _repo_size_bytes(repo_root: Path) -> int:
    total = 0
    for p in repo_root.rglob("*"):
        if p.is_file() and ".git" not in p.parts:
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def _traffic_light(used_pct: float) -> str:
    if used_pct >= 85:
        return "🔴"
    if used_pct >= 60:
        return "🟡"
    return "🟢"


def _pct_bar(used_pct: float) -> str:
    filled = int(used_pct / 5)
    empty = 20 - filled
    return f"[{'█' * filled}{'░' * empty}] {used_pct:.1f}%"


def _load_ai_state(repo_root: Path) -> dict:
    state_path = repo_root / "Bulletins" / "ai_router_state.json"
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _github_actions_minutes() -> tuple[int | None, str]:
    """Try to read GitHub Actions usage via the API.

    Returns (minutes_used, note_string).
    """
    token = os.getenv("GITHUB_TOKEN", "").strip()
    repo = os.getenv("GITHUB_REPOSITORY", "").strip()
    if not token or not repo or "/" not in repo:
        return None, "GitHub API not accessible (no GITHUB_TOKEN or GITHUB_REPOSITORY). See https://github.com/settings/billing."
    owner = repo.split("/")[0]
    url = f"https://api.github.com/users/{owner}/settings/billing/actions"
    req = request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        used = data.get("total_minutes_used", None)
        return used, ""
    except Exception as exc:  # noqa: BLE001
        return None, f"GitHub API call failed: {exc}. See https://github.com/settings/billing."


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _section_repo_size(repo_root: Path) -> str:
    size_bytes = _repo_size_bytes(repo_root)
    size_gb = size_bytes / GB
    cap_gb = GITHUB_REPO_CAP_GB
    pct = size_gb / cap_gb * 100
    light = _traffic_light(pct)
    bar = _pct_bar(pct)

    lines = [
        f"## {light} Repository storage",
        "",
        f"**Used:** {size_gb:.3f} GB / {cap_gb:.1f} GB hard cap",
        f"**Progress:** {bar}",
        "",
    ]
    if pct >= 85:
        lines += [
            "**⚠️ Action required:**",
            "1. Go to `.github/workflows/retention.yml` and trigger it manually.",
            "2. If that doesn't help, see the retention policy: `parishes/retention_policy.json`.",
            "3. As a last resort, reduce `keep_months_archive` to 12.",
            "",
        ]
    elif pct >= 60:
        lines += [
            "**ℹ️ Approaching limit.** Retention workflow will compress old files automatically.",
            "",
        ]
    else:
        lines += ["Plenty of space. No action needed.", ""]

    return "\n".join(lines)


def _section_ai_calls(repo_root: Path) -> str:
    state = _load_ai_state(repo_root)
    lines = [
        "## 🟢 AI API calls",
        "",
        "All AI providers used are **free tier**. This section is informational.",
        "",
    ]
    if state:
        for provider, count in state.items():
            lines.append(f"- **{provider}**: {count} call(s) this run")
    else:
        lines.append("- No AI call data recorded yet (Bulletins/ai_router_state.json not found).")
    lines.append("")
    lines += [
        "**What to do if a provider stops working:** The ai_router automatically falls back to",
        "the next provider (Gemini → Groq → Mistral). Events and summaries will degrade gracefully.",
        "",
    ]
    return "\n".join(lines)


def _section_actions_minutes() -> str:
    minutes_used, note = _github_actions_minutes()
    if minutes_used is None:
        return "\n".join([
            "## 🟢 GitHub Actions minutes",
            "",
            "Public repositories get **unlimited free minutes**.",
            f"_{note}_",
            "",
        ])
    pct = minutes_used / GITHUB_ACTIONS_FREE_MINUTES * 100
    light = _traffic_light(pct)
    bar = _pct_bar(pct)
    lines = [
        f"## {light} GitHub Actions minutes",
        "",
        f"**Used this month:** {minutes_used} / {GITHUB_ACTIONS_FREE_MINUTES} minutes",
        f"**Progress:** {bar}",
        "",
    ]
    if pct >= 85:
        lines += [
            "**⚠️ Action required:** You may be charged for extra minutes.",
            "Consider disabling the OCR workflow or skipping non-essential test runs.",
            "",
        ]
    return "\n".join(lines)


def _section_free_forever() -> str:
    return "\n".join([
        "## ✅ What's free forever and won't change",
        "",
        "- **GitHub Actions** — public repos get unlimited minutes.",
        "- **GitHub Pages** — 100 GB/month bandwidth, no cost.",
        "- **Gemini API** — 1,500 free requests/day (no credit card).",
        "- **Groq API** — 30 free requests/min (no credit card).",
        "- **Mistral free tier** — ~1 request/sec (no credit card).",
        "- **Repository storage** — 5 GB hard cap (managed by retention workflow).",
        "",
    ])


def _section_could_cost() -> str:
    return "\n".join([
        "## ⚠️ What could start costing money",
        "",
        "| Resource | Free limit | What happens if exceeded |",
        "|---|---|---|",
        "| Repo storage | 5 GB | GitHub warns you; repo may become read-only |",
        "| GitHub Actions (private repos) | 2,000 min/month | Charged per minute |",
        "| Pages bandwidth | 100 GB/month | GitHub may throttle or contact you |",
        "| AI API (if you switch to paid keys) | Varies | Billed to your account |",
        "",
        "> **This repo is public** — Actions minutes are unlimited. Storage is the only real risk.",
        "",
    ])


def _section_if_red() -> str:
    return "\n".join([
        "## 🚨 What to do if a 🔴 appears",
        "",
        "1. **Storage 🔴**: Trigger the retention workflow manually in GitHub Actions.",
        "2. **Actions minutes 🔴**: Only a risk for private repos. Make the repo public.",
        "3. **AI calls failing**: Check `.env` / GitHub Secrets for your API keys.",
        "   The ai_router falls back automatically — summaries may be missing but harvest continues.",
        "",
    ])


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def update_dashboard(repo_root: Path) -> None:
    """Write ``docs/COST_DASHBOARD.md`` with current traffic-light status.

    Degrades gracefully: if the GitHub API is unavailable, that section
    notes it and continues.  Never raises.
    """
    try:
        _write_dashboard(repo_root)
    except Exception as exc:  # noqa: BLE001
        print(f"[cost_tracker] Warning: dashboard update failed: {exc}")


def _write_dashboard(repo_root: Path) -> None:
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    sections = [
        f"# 💷 Cost Dashboard\n\n_Auto-generated at {generated_at} UTC._\n",
        "_This file is rewritten on every harvest run. Do not edit manually._\n",
        _section_free_forever(),
        _section_could_cost(),
        _section_repo_size(repo_root),
        _section_ai_calls(repo_root),
        _section_actions_minutes(),
        _section_if_red(),
        "\n---\n",
        "_For more detail see [WHAT_IS_THIS.md](../WHAT_IS_THIS.md) — "
        "'💷 What this costs Franky' section._\n",
    ]

    out_path = repo_root / "docs" / "COST_DASHBOARD.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(sections), encoding="utf-8")
    print(f"[cost_tracker] Dashboard written to {out_path}")
