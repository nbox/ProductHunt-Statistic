#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Product Hunt daily catalog updater.

What it does:
- Fetches launches for "today" via Product Hunt GraphQL.
- Writes/updates a daily report file: YYYY/MM/DD-MM-YYYY.md
- Updates README.md blocks:
  - Today section: summary + full table (no TOP_N limit)
  - Archive navigation: expandable by year and month

Important behavior:
- If there are **0 launches** for the selected day, the script does **nothing** (no file updates).

Env vars:
- PRODUCTHUNT_TOKEN (required)
- PH_TZ (default: America/Los_Angeles)
- DATE (optional override): YYYY-MM-DD – force a specific day in PH_TZ
"""

from __future__ import annotations

import html
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from urllib.request import Request, urlopen


PH_ENDPOINT = "https://api.producthunt.com/v2/api/graphql"
README_PATH = "README.md"

START_TODAY = "<!-- START:PH_TODAY -->"
END_TODAY = "<!-- END:PH_TODAY -->"

START_ARCHIVE = "<!-- START:ARCHIVE -->"
END_ARCHIVE = "<!-- END:ARCHIVE -->"


QUERY_POSTS = r"""
query Posts($first: Int, $after: String, $postedAfter: DateTime, $postedBefore: DateTime) {
  posts(first: $first, after: $after, postedAfter: $postedAfter, postedBefore: $postedBefore) {
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        id
        slug
        name
        tagline
        description
        url
        website
        votesCount
        commentsCount
      }
    }
  }
}
"""


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def md_escape_text(s: str) -> str:
    # Escape for Markdown tables (NOT HTML).
    return (s or "").replace("\n", " ").replace("|", "\\|").strip()


def safe_link(label: str, url: str) -> str:
    label = md_escape_text(label)
    url = (url or "").strip()
    if not url:
        return label
    return f"[{label}](<{url}>)"


def html_compact(s: str) -> str:
    # Escape for HTML-in-Markdown, keep newlines as <br>
    s = (s or "").strip()
    if not s:
        return ""
    s = html.escape(s)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    return s.replace("\n", "<br>")


def website_icon_link(website: str) -> str:
    w = (website or "").strip()
    if not w:
        return "—"
    # icon-only link (no full URL text)
    return f"[🔗](<{w}>)"


def build_description_cell(tagline: str, description: str) -> str:
    short = html_compact(tagline)
    full = html_compact(description)

    if not short and not full:
        return "—"

    if not short and full:
        # Fallback: short line from description
        short = full
        if len(short) > 180:
            short = short[:177].rstrip() + "…"

    if not full:
        return short

    return (
        f"{short}<br>"
        f"<details><summary><strong>Full description</strong></summary><br>"
        f"{full}<br></details>"
    )


def ph_call(token: str, query: str, variables: dict) -> dict:
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = Request(
        PH_ENDPOINT,
        data=payload,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    raw = urlopen(req, timeout=45).read().decode("utf-8")
    out = json.loads(raw)
    if out.get("errors"):
        raise RuntimeError(json.dumps(out["errors"], ensure_ascii=False))
    return out.get("data") or {}


def get_target_day(tz_name: str) -> tuple[datetime, datetime, str, str, str]:
    tz = ZoneInfo(tz_name)

    override = (os.getenv("DATE") or "").strip()
    if override:
        y, m, d = [int(x) for x in override.split("-")]
        start = datetime(y, m, d, 0, 0, 0, tzinfo=tz)
    else:
        now = datetime.now(tz)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    end = start + timedelta(days=1)

    label = start.strftime("%d-%m-%Y")
    year = start.strftime("%Y")
    month = start.strftime("%m")
    return start, end, label, year, month


def fetch_posts_for_day(token: str, start_local: datetime, end_local: datetime) -> list[dict]:
    after = None
    items: list[dict] = []

    while True:
        vars_ = {
            "first": 50,
            "after": after,
            "postedAfter": iso_z(start_local),
            "postedBefore": iso_z(end_local),
        }
        data = ph_call(token, QUERY_POSTS, vars_)
        conn = (data.get("posts") or {})
        edges = conn.get("edges") or []

        for e in edges:
            node = (e or {}).get("node")
            if node:
                items.append(node)

        page = conn.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            break
        after = page.get("endCursor")
        if not after:
            break

    return items


@dataclass
class DailyStats:
    launches: int
    total_votes: int
    avg_votes: float
    median_votes: float
    total_comments: int
    avg_comments: float
    median_comments: float


def compute_daily_stats(posts: list[dict]) -> DailyStats:
    votes = [int(p.get("votesCount") or 0) for p in posts]
    comments = [int(p.get("commentsCount") or 0) for p in posts]
    n = len(posts)

    votes_sorted = sorted(votes)
    comments_sorted = sorted(comments)

    total_votes = sum(votes)
    total_comments = sum(comments)

    avg_votes = (total_votes / n) if n else 0.0
    avg_comments = (total_comments / n) if n else 0.0

    if n == 0:
        median_votes = 0.0
        median_comments = 0.0
    elif n % 2 == 1:
        median_votes = float(votes_sorted[n // 2])
        median_comments = float(comments_sorted[n // 2])
    else:
        median_votes = (votes_sorted[n // 2 - 1] + votes_sorted[n // 2]) / 2.0
        median_comments = (comments_sorted[n // 2 - 1] + comments_sorted[n // 2]) / 2.0

    return DailyStats(
        launches=n,
        total_votes=total_votes,
        avg_votes=avg_votes,
        median_votes=median_votes,
        total_comments=total_comments,
        avg_comments=avg_comments,
        median_comments=median_comments,
    )


def render_posts_table(posts: list[dict]) -> str:
    lines: list[str] = []
    lines.append("| # | App | Description | Votes | Comments | Website |")
    lines.append("|---:|---|---|---:|---:|---|")

    posts_sorted = sorted(posts, key=lambda p: int(p.get("votesCount") or 0), reverse=True)

    for i, p in enumerate(posts_sorted, 1):
        name = md_escape_text(p.get("name") or "")
        ph_url = (p.get("url") or "").strip()
        app_cell = safe_link(name, ph_url) if ph_url else name

        desc_cell = build_description_cell(p.get("tagline") or "", p.get("description") or "")

        votes = int(p.get("votesCount") or 0)
        comments = int(p.get("commentsCount") or 0)

        website_cell = website_icon_link(p.get("website") or "")

        lines.append(
            f"| {i} | {app_cell} | {desc_cell} | {votes} | {comments} | {website_cell} |"
        )

    return "\n".join(lines) + "\n"


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def write_text(path: str, content: str) -> None:
    ensure_dir(os.path.dirname(path) or ".")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def replace_block(text: str, start: str, end: str, new_block: str) -> str:
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), flags=re.DOTALL)
    replacement = f"{start}\n{new_block}\n{end}"
    if pattern.search(text):
        return pattern.sub(replacement, text, count=1)
    return text.rstrip() + "\n\n" + replacement + "\n"


def scan_archive_nav() -> str:
    years: list[str] = []
    for entry in os.listdir("."):
        if entry.isdigit() and len(entry) == 4 and os.path.isdir(entry):
            years.append(entry)
    years.sort(reverse=True)

    if not years:
        return "_No reports yet._"

    lines: list[str] = []
    for y in years:
        months: list[str] = []
        for m in os.listdir(y):
            if m.isdigit() and len(m) == 2 and os.path.isdir(os.path.join(y, m)):
                months.append(m)
        months.sort(reverse=True)

        lines.append("<details>")
        lines.append(f"<summary>{y}</summary>\n")

        for m in months:
            month_dir = os.path.join(y, m)
            files = [f for f in os.listdir(month_dir) if f.lower().endswith(".md")]

            def sort_key(fn: str):
                base = fn[:-3]
                try:
                    d, mm, yy = base.split("-")
                    return datetime(int(yy), int(mm), int(d))
                except Exception:
                    return datetime.min

            files.sort(key=sort_key, reverse=True)

            lines.append("  <details>")
            lines.append(f"  <summary>{m}</summary>\n")

            if not files:
                lines.append("  _Empty_\n")
                lines.append("  </details>\n")
                continue

            for fn in files:
                rel = f"{y}/{m}/{fn}"
                title = fn[:-3]
                lines.append(f"  - [{title}]({rel})")

            lines.append("\n  </details>\n")

        lines.append("</details>\n")

    return "\n".join(lines).rstrip() + "\n"


def build_daily_report_md(
    tz_name: str,
    label_dd_mm_yyyy: str,
    stats: DailyStats,
    posts: list[dict],
    rel_link_to_today: str,
) -> str:
    header = f"# Product Hunt — launches for {label_dd_mm_yyyy}\n"
    sub = f"_Timezone for “today”: `{tz_name}`. Source: Product Hunt API._\n\n"
    follow_me = "[![Follow me on Product Hunt](https://img.shields.io/badge/Follow%20me%20on%20Product%20Hunt-@nbox-orange?style=for-the-badge)](https://www.producthunt.com/@nbox)\n\n"

    summary = []
    summary.append("## Summary\n")
    summary.append(f"- Launches: **{stats.launches}**")
    summary.append(f"- Total votes: **{stats.total_votes}**")
    summary.append(f"- Avg / Median votes: **{stats.avg_votes:.2f} / {stats.median_votes:.2f}**")
    summary.append(f"- Total comments: **{stats.total_comments}**")
    summary.append(f"- Avg / Median comments: **{stats.avg_comments:.2f} / {stats.median_comments:.2f}**")
    summary.append(f"- Report file: {safe_link(label_dd_mm_yyyy, rel_link_to_today)}")
    summary.append("\n")

    launches = []
    launches.append("## Launches (sorted by votes)\n")
    launches.append(render_posts_table(posts))

    return header + follow_me + "\n".join(summary) + "\n" + "\n".join(launches)



def build_today_readme_block(
    tz_name: str,
    label_dd_mm_yyyy: str,
    stats: DailyStats,
    posts: list[dict],
    rel_link_to_today: str,
) -> str:
    lines: list[str] = []
    lines.append(f"### {label_dd_mm_yyyy} ({tz_name})\n")
    lines.append(f"- Launches: **{stats.launches}**")
    lines.append(f"- Total votes: **{stats.total_votes}**")
    lines.append(f"- Avg / Median votes: **{stats.avg_votes:.2f} / {stats.median_votes:.2f}**")
    lines.append(f"- Total comments: **{stats.total_comments}**")
    lines.append(f"- Avg / Median comments: **{stats.avg_comments:.2f} / {stats.median_comments:.2f}**")
    lines.append(f"- Full report: {safe_link(label_dd_mm_yyyy, rel_link_to_today)}\n")
    lines.append(render_posts_table(posts))
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    token = (os.getenv("PRODUCTHUNT_TOKEN") or "").strip()
    if not token:
        print("Missing env PRODUCTHUNT_TOKEN", file=sys.stderr)
        return 2

    tz_name = (os.getenv("PH_TZ") or "America/Los_Angeles").strip() or "America/Los_Angeles"

    start_local, end_local, label, year, month = get_target_day(tz_name)

    posts = fetch_posts_for_day(token, start_local, end_local)

    # If there are no launches yet, do not touch files at all.
    if not posts:
        print("No launches found for today. Skipping all updates.")
        return 0

    stats = compute_daily_stats(posts)

    daily_filename = f"{label}.md"
    daily_path = os.path.join(year, month, daily_filename)
    rel_link_to_today = f"{year}/{month}/{daily_filename}"

    daily_md = build_daily_report_md(
        tz_name=tz_name,
        label_dd_mm_yyyy=label,
        stats=stats,
        posts=posts,
        rel_link_to_today=rel_link_to_today,
    )
    write_text(daily_path, daily_md)
    print(f"Wrote/updated: {daily_path}")

    if not os.path.exists(README_PATH):
        print("README.md not found. Create it first.", file=sys.stderr)
        return 3

    with open(README_PATH, "r", encoding="utf-8") as f:
        readme = f.read()

    today_block = build_today_readme_block(
        tz_name=tz_name,
        label_dd_mm_yyyy=label,
        stats=stats,
        posts=posts,
        rel_link_to_today=rel_link_to_today,
    )
    archive_block = scan_archive_nav()

    readme = replace_block(readme, START_TODAY, END_TODAY, today_block)
    readme = replace_block(readme, START_ARCHIVE, END_ARCHIVE, archive_block)

    write_text(README_PATH, readme)
    print("README updated")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
