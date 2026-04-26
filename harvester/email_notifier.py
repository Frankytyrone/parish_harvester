"""
email_notifier.py — Email notification support for the Parish Bulletin Harvester.

Sends a harvest summary email after each harvest completes.

Configuration (environment variables):
    HARVEST_EMAIL_TO      — recipient address (required to enable notifications)
    HARVEST_EMAIL_FROM    — sender address (default: harvester@localhost)
    EMAIL_PROVIDER        — 'smtp' (default), 'sendgrid', or 'mailgun'

    SMTP provider:
        SMTP_HOST         — SMTP server hostname (default: smtp.gmail.com)
        SMTP_PORT         — SMTP server port (default: 587)
        SMTP_USER         — SMTP login username
        SMTP_PASSWORD     — SMTP login password

    SendGrid provider:
        SENDGRID_API_KEY  — SendGrid API key

    Mailgun provider:
        MAILGUN_API_KEY   — Mailgun API key
        MAILGUN_DOMAIN    — Mailgun sending domain
"""
from __future__ import annotations

import json
import os
import smtplib
from datetime import date, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path


# ---------------------------------------------------------------------------
# HTML / plain-text generation
# ---------------------------------------------------------------------------

def _format_date_long(date_str: str) -> str:
    """Convert 'YYYY-MM-DD' to e.g. 'Sunday, April 26, 2026'."""
    try:
        d = date.fromisoformat(date_str)
        return d.strftime("%A, %B %-d, %Y")
    except Exception:
        return date_str


def _next_sunday(date_str: str) -> str:
    """Return the Sunday after the given date string."""
    try:
        d = date.fromisoformat(date_str)
        days_until_next_sunday = (6 - d.weekday()) % 7 or 7
        return (d + timedelta(days=days_until_next_sunday)).strftime("%A, %B %-d, %Y")
    except Exception:
        return "next Sunday"


def _pct(count: int, total: int) -> str:
    if total == 0:
        return "0%"
    return f"{round(count / total * 100)}%"


def generate_email_html(report: dict, duration_seconds: float | None = None) -> str:
    """Return an HTML email body for the harvest report."""
    summary = report.get("summary", {})
    failed = report.get("failed", [])
    target_date = report.get("target_date", "")

    downloaded = summary.get("downloaded", 0)
    html_links = summary.get("html_links", 0)
    fail_count = summary.get("failed", 0)
    total = downloaded + html_links + fail_count

    long_date = _format_date_long(target_date)
    next_harvest = _next_sunday(target_date)

    duration_str = ""
    if duration_seconds is not None:
        mins = int(duration_seconds // 60)
        secs = int(duration_seconds % 60)
        if mins > 0:
            duration_str = f"{mins} minute{'s' if mins != 1 else ''} {secs} second{'s' if secs != 1 else ''}"
        else:
            duration_str = f"{secs} second{'s' if secs != 1 else ''}"

    failure_section = _generate_failure_section_html(failed)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Parish Bulletin Harvest Report</title>
  <style>
    body {{ margin: 0; padding: 0; background: #f3f4f6; font-family: system-ui, -apple-system, sans-serif; }}
    .container {{ max-width: 600px; margin: 20px auto; background: #ffffff;
                 padding: 30px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
    .header {{ text-align: center; border-bottom: 2px solid #3b82f6; padding-bottom: 20px; margin-bottom: 20px; }}
    .header h1 {{ margin: 0 0 8px 0; font-size: 22px; color: #1e3a5f; }}
    .header p {{ margin: 0; color: #6b7280; font-size: 14px; }}
    .meta {{ color: #374151; font-size: 14px; margin-bottom: 20px; }}
    .meta span {{ font-weight: bold; color: #111827; }}
    .stats {{ display: table; width: 100%; border-collapse: separate; border-spacing: 8px; margin: 20px 0; }}
    .stats-row {{ display: table-row; }}
    .stat-card {{ display: table-cell; background: #f9fafb; padding: 16px 10px;
                 border-radius: 6px; text-align: center; border: 1px solid #e5e7eb; width: 33%; }}
    .stat-number {{ font-size: 28px; font-weight: bold; line-height: 1.2; }}
    .stat-label {{ font-size: 12px; color: #6b7280; margin-top: 4px; }}
    .success {{ color: #16a34a; }}
    .failure {{ color: #dc2626; }}
    .neutral {{ color: #2563eb; }}
    .failures-box {{ background: #fef2f2; padding: 16px; border-radius: 6px;
                    border-left: 4px solid #ef4444; margin: 20px 0; }}
    .failures-box h3 {{ margin: 0 0 10px 0; color: #dc2626; font-size: 15px; }}
    .failures-box ul {{ margin: 0; padding-left: 20px; }}
    .failures-box li {{ margin: 6px 0; font-size: 14px; color: #374151; }}
    .actions {{ text-align: center; margin: 24px 0; }}
    .btn {{ display: inline-block; background: #3b82f6; color: #ffffff !important;
           padding: 10px 20px; border-radius: 6px; text-decoration: none;
           font-size: 14px; font-weight: 600; margin: 4px; }}
    .footer {{ text-align: center; font-size: 12px; color: #9ca3af; margin-top: 24px;
              border-top: 1px solid #e5e7eb; padding-top: 16px; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>📋 Parish Bulletin Harvest Complete</h1>
      <p>{long_date}</p>
    </div>

    <div class="meta">
      Date: <span>{long_date}</span>{"<br>Duration: <span>" + duration_str + "</span>" if duration_str else ""}
    </div>

    <div class="stats">
      <div class="stats-row">
        <div class="stat-card">
          <div class="stat-number success">✅ {downloaded}</div>
          <div class="stat-label">Downloaded ({_pct(downloaded, total)})</div>
        </div>
        <div class="stat-card">
          <div class="stat-number failure">❌ {fail_count}</div>
          <div class="stat-label">Failed ({_pct(fail_count, total)})</div>
        </div>
        <div class="stat-card">
          <div class="stat-number neutral">🔗 {html_links}</div>
          <div class="stat-label">HTML Links ({_pct(html_links, total)})</div>
        </div>
      </div>
    </div>

    {failure_section}

    <div class="footer">
      <p>Next harvest: {next_harvest} at 8:00 AM</p>
      <p>Parish Bulletin Harvester v2 &mdash; Automated by GitHub Actions</p>
    </div>
  </div>
</body>
</html>"""
    return html


def _generate_failure_section_html(failures: list[dict]) -> str:
    if not failures:
        return ""
    items = "\n".join(
        f"        <li><strong>{f.get('display_name', f.get('parish', 'Unknown'))}</strong>: "
        f"{f.get('error', 'unknown error')}</li>"
        for f in failures[:5]
    )
    return f"""    <div class="failures-box">
      <h3>⚠️ Recent Failures</h3>
      <ul>
{items}
      </ul>
    </div>"""


def generate_email_plain(report: dict, duration_seconds: float | None = None) -> str:
    """Return a plain-text email body for the harvest report."""
    summary = report.get("summary", {})
    failed = report.get("failed", [])
    target_date = report.get("target_date", "")

    downloaded = summary.get("downloaded", 0)
    html_links = summary.get("html_links", 0)
    fail_count = summary.get("failed", 0)
    total = downloaded + html_links + fail_count

    long_date = _format_date_long(target_date)
    next_harvest = _next_sunday(target_date)

    duration_str = ""
    if duration_seconds is not None:
        mins = int(duration_seconds // 60)
        secs = int(duration_seconds % 60)
        if mins > 0:
            duration_str = f"\nDuration: {mins} minute{'s' if mins != 1 else ''} {secs} second{'s' if secs != 1 else ''}"

    lines = [
        "────────────────────────────────────────────────",
        "📋 Parish Bulletin Harvest Report",
        "────────────────────────────────────────────────",
        "",
        f"Date: {long_date}{duration_str}",
        "",
        "Results:",
        f"  ✅ Downloaded: {downloaded} parishes ({_pct(downloaded, total)})",
        f"  ❌ Failed: {fail_count} parishes ({_pct(fail_count, total)})",
        f"  🔗 HTML Links: {html_links} parishes ({_pct(html_links, total)})",
    ]

    if failed:
        lines += ["", "Recent Failures:"]
        for f in failed[:5]:
            name = f.get("display_name", f.get("parish", "Unknown"))
            error = f.get("error", "unknown error")
            lines.append(f"  • {name} ({error})")

    lines += [
        "",
        f"Next harvest: {next_harvest} at 8:00 AM",
        "",
        "────────────────────────────────────────────────",
        "Parish Bulletin Harvester v2",
        "Automated by GitHub Actions",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Email provider implementations
# ---------------------------------------------------------------------------

def _send_smtp(subject: str, html_body: str, plain_body: str, to: str) -> None:
    """Send email via SMTP (e.g. Gmail, Outlook)."""
    from_addr = os.environ.get("HARVEST_EMAIL_FROM") or os.environ.get("SMTP_USER", "harvester@localhost")
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASSWORD", "")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to
    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(host, port) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        if user and password:
            server.login(user, password)
        server.send_message(msg)


def _send_sendgrid(subject: str, html_body: str, plain_body: str, to: str) -> None:
    """Send email via SendGrid API."""
    try:
        import sendgrid  # type: ignore[import]
        from sendgrid.helpers.mail import Mail  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "sendgrid package is not installed. "
            "Run: pip install sendgrid"
        ) from exc

    api_key = os.environ.get("SENDGRID_API_KEY", "")
    from_addr = os.environ.get("HARVEST_EMAIL_FROM", "harvester@localhost")

    sg = sendgrid.SendGridAPIClient(api_key=api_key)
    message = Mail(
        from_email=from_addr,
        to_emails=to,
        subject=subject,
        plain_text_content=plain_body,
        html_content=html_body,
    )
    response = sg.send(message)
    status = response.status_code
    if status not in (200, 202):
        raise RuntimeError(f"SendGrid returned unexpected status: {status}")


def _send_mailgun(subject: str, html_body: str, plain_body: str, to: str) -> None:
    """Send email via Mailgun API."""
    try:
        import requests  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "requests package is not installed. "
            "Run: pip install requests"
        ) from exc

    api_key = os.environ.get("MAILGUN_API_KEY", "")
    domain = os.environ.get("MAILGUN_DOMAIN", "")
    from_addr = os.environ.get("HARVEST_EMAIL_FROM", f"harvester@{domain}")

    if not domain:
        raise RuntimeError("MAILGUN_DOMAIN environment variable is not set.")

    response = requests.post(
        f"https://api.mailgun.net/v3/{domain}/messages",
        auth=("api", api_key),
        data={
            "from": from_addr,
            "to": to,
            "subject": subject,
            "text": plain_body,
            "html": html_body,
        },
        timeout=30,
    )
    response.raise_for_status()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def send_harvest_notification(
    report_path: Path,
    duration_seconds: float | None = None,
) -> None:
    """Send an email notification after a harvest completes.

    Does nothing if HARVEST_EMAIL_TO is not set, so it is always safe to call.

    Args:
        report_path: Path to the report.json file written by generate_report().
        duration_seconds: How long the harvest took (optional, shown in email).
    """
    to_email = os.environ.get("HARVEST_EMAIL_TO", "").strip()
    if not to_email:
        print("ℹ️  Email notifications not configured (set HARVEST_EMAIL_TO to enable)")
        return

    if not report_path.exists():
        print(f"⚠️  Cannot send notification: report not found at {report_path}")
        return

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"⚠️  Cannot send notification: failed to read report: {exc}")
        return

    target_date = report.get("target_date", "unknown")
    subject = f"✅ Parish Harvest Complete - {target_date}"

    html_body = generate_email_html(report, duration_seconds)
    plain_body = generate_email_plain(report, duration_seconds)

    provider = os.environ.get("EMAIL_PROVIDER", "smtp").lower()

    try:
        if provider == "sendgrid":
            _send_sendgrid(subject, html_body, plain_body, to_email)
        elif provider == "mailgun":
            _send_mailgun(subject, html_body, plain_body, to_email)
        else:
            _send_smtp(subject, html_body, plain_body, to_email)
        print(f"📧 Harvest notification sent to {to_email}")
    except Exception as exc:
        print(f"⚠️  Failed to send harvest notification: {exc}")
