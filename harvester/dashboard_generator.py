"""
dashboard_generator.py — Generate an interactive HTML dashboard from harvest data.

Reads report.json and harvest_log.json to produce a self-contained HTML file
with summary cards, a success-rate trend chart, a parish status grid, and a
failure-analysis section.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


def generate_dashboard(
    report_path: Path,
    log_path: Path,
    output_path: Path,
) -> None:
    """Generate an interactive HTML dashboard from harvest data.

    Parameters
    ----------
    report_path:
        Path to ``report.json`` produced by :func:`harvester.report.generate_report`.
    log_path:
        Path to ``harvest_log.json`` produced by :mod:`harvester.harvest_log`.
        May not exist yet on the very first run.
    output_path:
        Destination path for the generated ``dashboard.html``.
    """
    try:
        report: dict = json.loads(report_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        report = {
            "target_date": "unknown",
            "summary": {"downloaded": 0, "html_links": 0, "failed": 0},
            "downloaded": [],
            "html_links": [],
            "failed": [],
        }

    try:
        log: list[dict] = json.loads(log_path.read_text(encoding="utf-8"))
        if not isinstance(log, list):
            log = []
    except (FileNotFoundError, json.JSONDecodeError):
        log = []

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Parish Bulletin Harvest Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: system-ui, -apple-system, sans-serif;
            background: #f3f4f6;
            padding: 20px;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        .header {{
            background: white;
            padding: 30px;
            border-radius: 12px;
            margin-bottom: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .header h1 {{ font-size: 28px; margin-bottom: 8px; }}
        .header p {{ color: #6b7280; font-size: 16px; }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }}
        .stat-card {{
            background: white;
            padding: 25px;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .stat-number {{
            font-size: 42px;
            font-weight: bold;
            margin-bottom: 5px;
        }}
        .stat-label {{
            color: #6b7280;
            font-size: 13px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}
        .success {{ color: #22c55e; }}
        .failure {{ color: #ef4444; }}
        .neutral {{ color: #3b82f6; }}
        .chart-container {{
            background: white;
            padding: 25px;
            border-radius: 12px;
            margin-bottom: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .chart-container h2 {{
            margin-bottom: 20px;
            font-size: 18px;
        }}
        .chart-wrapper {{
            position: relative;
            height: 260px;
        }}
        .parish-grid {{
            background: white;
            border-radius: 12px;
            padding: 25px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }}
        .parish-grid h2 {{
            margin-bottom: 16px;
            font-size: 18px;
        }}
        .parish-table {{
            width: 100%;
            border-collapse: collapse;
        }}
        .parish-table th {{
            text-align: left;
            padding: 10px 12px;
            background: #f3f4f6;
            font-size: 13px;
            color: #374151;
            border-bottom: 2px solid #e5e7eb;
        }}
        .parish-table td {{
            padding: 11px 12px;
            border-bottom: 1px solid #e5e7eb;
            font-size: 14px;
            vertical-align: middle;
        }}
        .parish-table tr:last-child td {{ border-bottom: none; }}
        .parish-table tr:hover td {{ background: #f9fafb; }}
        .filter-bar {{
            background: white;
            padding: 16px 20px;
            border-radius: 12px;
            margin-bottom: 20px;
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            align-items: center;
        }}
        .filter-bar span {{
            font-size: 14px;
            color: #6b7280;
            margin-right: 4px;
        }}
        .filter-btn {{
            padding: 8px 16px;
            border: 1px solid #d1d5db;
            border-radius: 8px;
            background: white;
            cursor: pointer;
            transition: all 0.15s;
            font-size: 14px;
        }}
        .filter-btn:hover {{ background: #f3f4f6; }}
        .filter-btn.active {{
            background: #3b82f6;
            color: white;
            border-color: #3b82f6;
        }}
        .failure-section {{
            background: white;
            border-radius: 12px;
            padding: 25px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }}
        .failure-section h2 {{
            margin-bottom: 16px;
            font-size: 18px;
        }}
        .failure-item {{
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 10px 0;
            border-bottom: 1px solid #e5e7eb;
            font-size: 14px;
        }}
        .failure-item:last-child {{ border-bottom: none; }}
        .failure-rank {{
            width: 28px;
            height: 28px;
            border-radius: 50%;
            background: #fee2e2;
            color: #ef4444;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            font-size: 13px;
            flex-shrink: 0;
        }}
        .failure-name {{ font-weight: 500; flex: 1; }}
        .failure-meta {{ color: #6b7280; font-size: 13px; }}
        .badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 99px;
            font-size: 12px;
            font-weight: 500;
        }}
        .badge-success {{ background: #dcfce7; color: #16a34a; }}
        .badge-failed {{ background: #fee2e2; color: #dc2626; }}
        .badge-html {{ background: #dbeafe; color: #1d4ed8; }}
        @media (max-width: 640px) {{
            .header h1 {{ font-size: 20px; }}
            .stat-number {{ font-size: 32px; }}
        }}
    </style>
</head>
<body>
<div class="container">

    <div class="header">
        <h1>📋 Parish Bulletin Harvest Dashboard</h1>
        <p>Last updated: {report.get("target_date", "unknown")}</p>
    </div>

    {_summary_cards(report)}

    {_filter_bar()}

    {_success_chart(log)}

    {_parish_grid(report)}

    {_failure_analysis(log)}

</div>
<script>
{_javascript(report, log)}
</script>
</body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(f"📊 Dashboard created: {output_path}")
    print(f"🌐 Open in browser: file://{output_path.resolve()}")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _summary_cards(report: dict) -> str:
    summary = report.get("summary", {})
    downloaded = summary.get("downloaded", 0)
    failed = summary.get("failed", 0)
    html_links = summary.get("html_links", 0)
    total = downloaded + failed
    success_rate = (downloaded / total * 100) if total > 0 else 0.0

    return f"""
    <div class="stats">
        <div class="stat-card">
            <div class="stat-number success">{downloaded}</div>
            <div class="stat-label">✅ Downloaded</div>
        </div>
        <div class="stat-card">
            <div class="stat-number failure">{failed}</div>
            <div class="stat-label">❌ Failed</div>
        </div>
        <div class="stat-card">
            <div class="stat-number neutral">{success_rate:.1f}%</div>
            <div class="stat-label">📈 Success Rate</div>
        </div>
        <div class="stat-card">
            <div class="stat-number neutral">{html_links}</div>
            <div class="stat-label">🔗 HTML Links</div>
        </div>
    </div>
"""


def _filter_bar() -> str:
    return """
    <div class="filter-bar">
        <span>Filter:</span>
        <button class="filter-btn active" data-filter="all">All Parishes</button>
        <button class="filter-btn" data-filter="success">✅ Success</button>
        <button class="filter-btn" data-filter="failed">❌ Failed</button>
        <button class="filter-btn" data-filter="html">🔗 HTML Only</button>
    </div>
"""


def _success_chart(log: list[dict]) -> str:
    """Build weekly success-rate labels and data from the harvest log."""
    weeks, rates = _weekly_success_rates(log, num_weeks=8)
    labels_json = json.dumps(weeks)
    data_json = json.dumps(rates)

    return f"""
    <div class="chart-container">
        <h2>📈 Success Rate Trend (Last 8 Weeks)</h2>
        <div class="chart-wrapper">
            <canvas id="successChart"></canvas>
        </div>
    </div>
    <script>
    (function() {{
        var ctx = document.getElementById('successChart').getContext('2d');
        new Chart(ctx, {{
            type: 'line',
            data: {{
                labels: {labels_json},
                datasets: [{{
                    label: 'Success Rate (%)',
                    data: {data_json},
                    borderColor: '#22c55e',
                    backgroundColor: 'rgba(34, 197, 94, 0.12)',
                    tension: 0.4,
                    fill: true,
                    pointRadius: 5,
                    pointBackgroundColor: '#22c55e'
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{ display: false }},
                    tooltip: {{
                        callbacks: {{
                            label: function(ctx) {{
                                return ctx.parsed.y !== null ? ctx.parsed.y.toFixed(1) + '%' : 'No data';
                            }}
                        }}
                    }}
                }},
                scales: {{
                    y: {{
                        min: 0,
                        max: 100,
                        ticks: {{
                            callback: function(v) {{ return v + '%'; }}
                        }}
                    }}
                }}
            }}
        }});
    }})();
    </script>
"""


def _parish_grid(report: dict) -> str:
    rows_html = []

    all_parishes: list[tuple[dict, str]] = (
        [(p, "success") for p in report.get("downloaded", [])]
        + [(p, "html") for p in report.get("html_links", [])]
        + [(p, "failed") for p in report.get("failed", [])]
    )
    all_parishes.sort(key=lambda x: (x[0].get("display_name") or x[0].get("parish", "")).lower())

    for parish_data, status in all_parishes:
        name = parish_data.get("display_name") or parish_data.get("parish", "Unknown")
        url = parish_data.get("url", "")
        error = parish_data.get("error", "")
        ts = parish_data.get("timestamp", report.get("target_date", ""))

        if status == "success":
            badge = '<span class="badge badge-success">✅ Downloaded</span>'
            detail = f'<a href="{url}" target="_blank" rel="noopener noreferrer" style="color:#3b82f6;text-decoration:none;font-size:13px;">{url[:60]}{"…" if len(url) > 60 else ""}</a>' if url else "—"
        elif status == "html":
            badge = '<span class="badge badge-html">🔗 HTML Link</span>'
            detail = f'<a href="{url}" target="_blank" rel="noopener noreferrer" style="color:#3b82f6;text-decoration:none;font-size:13px;">{url[:60]}{"…" if len(url) > 60 else ""}</a>' if url else "—"
        else:
            badge = '<span class="badge badge-failed">❌ Failed</span>'
            detail = f'<span style="color:#ef4444;font-size:13px;">{error[:80]}</span>' if error else "—"

        rows_html.append(
            f'<tr data-status="{status}">'
            f"<td>{name}</td>"
            f"<td>{badge}</td>"
            f"<td style='color:#6b7280;font-size:13px;'>{ts}</td>"
            f"<td>{detail}</td>"
            f"</tr>"
        )

    table_body = "\n".join(rows_html) if rows_html else '<tr><td colspan="4" style="text-align:center;color:#6b7280;padding:20px;">No parish data available.</td></tr>'

    return f"""
    <div class="parish-grid">
        <h2>⛪ Parish Status</h2>
        <table class="parish-table">
            <thead>
                <tr>
                    <th>Parish Name</th>
                    <th>Status</th>
                    <th>Date</th>
                    <th>Detail / URL</th>
                </tr>
            </thead>
            <tbody id="parishTableBody">
{table_body}
            </tbody>
        </table>
    </div>
"""


def _failure_analysis(log: list[dict]) -> str:
    """Show top failing parishes over the last 4 weeks."""
    if not log:
        return """
    <div class="failure-section">
        <h2>🔥 Top Failures (Last 4 Weeks)</h2>
        <p style="color:#6b7280;font-size:14px;">No harvest log data available yet.</p>
    </div>
"""

    cutoff = datetime.now(timezone.utc) - timedelta(weeks=4)
    fail_counts: dict[str, dict] = defaultdict(lambda: {"count": 0, "total": 0, "errors": [], "display_name": ""})

    # Count per parish
    parish_totals: dict[str, int] = defaultdict(int)
    for entry in log:
        ts_str = entry.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
        if ts < cutoff:
            continue
        key = entry.get("parish_key", "")
        display = entry.get("display_name", key)
        parish_totals[key] += 1
        fail_counts[key]["display_name"] = display
        fail_counts[key]["total"] = parish_totals[key]
        if entry.get("status") == "failed":
            fail_counts[key]["count"] += 1
            err = entry.get("error", "")
            if err and err not in fail_counts[key]["errors"]:
                fail_counts[key]["errors"].append(err)

    # Only keep parishes that actually failed at least once
    failing = {k: v for k, v in fail_counts.items() if v["count"] > 0}
    ranked = sorted(failing.items(), key=lambda x: x[1]["count"], reverse=True)[:10]

    if not ranked:
        return """
    <div class="failure-section">
        <h2>🔥 Top Failures (Last 4 Weeks)</h2>
        <p style="color:#22c55e;font-size:14px;">🎉 No failures recorded in the last 4 weeks!</p>
    </div>
"""

    items_html = []
    for idx, (key, data) in enumerate(ranked, start=1):
        display = data["display_name"] or key
        fail_n = data["count"]
        total_n = data["total"]
        main_error = data["errors"][0][:60] if data["errors"] else "Unknown"
        items_html.append(
            f'<div class="failure-item">'
            f'<div class="failure-rank">{idx}</div>'
            f'<div class="failure-name">{display}</div>'
            f'<div class="failure-meta">{fail_n}/{total_n} runs — {main_error}</div>'
            f"</div>"
        )

    return f"""
    <div class="failure-section">
        <h2>🔥 Top Failures (Last 4 Weeks)</h2>
        {"".join(items_html)}
    </div>
"""


def _javascript(report: dict, log: list[dict]) -> str:
    """Return JavaScript for the filter buttons."""
    return """
    // Filter buttons
    document.querySelectorAll('.filter-btn').forEach(function(btn) {
        btn.addEventListener('click', function() {
            document.querySelectorAll('.filter-btn').forEach(function(b) {
                b.classList.remove('active');
            });
            btn.classList.add('active');
            var filter = btn.getAttribute('data-filter');
            document.querySelectorAll('#parishTableBody tr').forEach(function(row) {
                if (filter === 'all' || row.getAttribute('data-status') === filter) {
                    row.style.display = '';
                } else {
                    row.style.display = 'none';
                }
            });
        });
    });
"""


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _weekly_success_rates(log: list[dict], num_weeks: int = 8) -> tuple[list[str], list[float | None]]:
    """Compute per-week success rates from the harvest log.

    Returns a tuple of (week_labels, rates) suitable for Chart.js.
    Weeks are ordered oldest → newest.  Weeks with no data get ``None``.
    """
    if not log:
        labels = [f"Week {i+1}" for i in range(num_weeks)]
        return labels, [None] * num_weeks

    now = datetime.now(timezone.utc)
    # Week boundaries: week 0 = oldest, week n-1 = current
    week_starts = [now - timedelta(weeks=(num_weeks - i)) for i in range(num_weeks)]
    week_ends = week_starts[1:] + [now + timedelta(days=1)]

    totals = [0] * num_weeks
    oks = [0] * num_weeks

    for entry in log:
        ts_str = entry.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
        for i, (ws, we) in enumerate(zip(week_starts, week_ends)):
            if ws <= ts < we:
                totals[i] += 1
                if entry.get("status") == "ok":
                    oks[i] += 1
                break

    labels: list[str] = []
    rates: list[float | None] = []
    for i, ws in enumerate(week_starts):
        labels.append(ws.strftime("%d %b").lstrip("0") or ws.strftime("%d %b"))
        if totals[i] == 0:
            rates.append(None)
        else:
            rates.append(round(oks[i] / totals[i] * 100, 1))

    return labels, rates
