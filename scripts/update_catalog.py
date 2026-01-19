
```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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
        name
        tagline
        url
        votesCount
        makers { name username url }
      }
    }
  }
}
"""


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def md_escape(s: str) -> str:
    return (s or "").replace("\n", " ").replace("|", "\\|").strip()


def safe_link(label: str, url: str) -> str:
    label = md_escape(label)
    url = (url or "").strip()
    if not url:
        return label
    return f"[{label}](<{url}>)"


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
    """
    Returns:
    - start_local, end_local: day boundaries in local timezone
    - label_dd_mm_yyyy: for filenames and headers (DD-MM-YYYY)
    - year, month: directory names
    """
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
            "first": 20,
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
    count: int
    total_votes: int
    avg_votes: float
    median_votes: float
    unique_makers: int
    top_by_votes: list[dict]
    prolific_maker: str


def compute_daily_stats(posts: list[dict], top_n: int = 10) -> DailyStats:
    votes = [int(p.get("votesCount") or 0) for p in posts]
    votes_sorted = sorted(votes)
    count = len(posts)
    total = sum(votes)

    avg = (total / count) if count else 0.0

    if count == 0:
        median = 0.0
    elif count % 2 == 1:
        median = float(votes_sorted[count // 2])
    else:
        median = (votes_sorted[count // 2 - 1] + votes_sorted[count // 2]) / 2.0

    maker_key_counts: dict[str, int] = {}
    maker_unique_set: set[str] = set()

    for p in posts:
        for m in (p.get("makers") or []):
            username = (m.get("username") or "").strip()
            name = (m.get("name") or "").strip()
            key = username or name
            if key:
                maker_unique_set.add(key)
                maker_key_counts[key] = maker_key_counts.get(key, 0) + 1

    prolific = "—"
    if maker_key_counts:
        key = max(maker_key_counts.items(), key=lambda kv: (kv[1], kv[0]))[0]
        prolific = f"{key} ({maker_key_counts[key]} launches)"

    top = sorted(posts, key=lambda p: int(p.get("votesCount") or 0), reverse=True)[:top_n]

    return DailyStats(
        count=count,
        total_votes=total,
        avg_votes=avg,
        median_votes=median,
        unique_makers=len(maker_unique_set),
        top_by_votes=top,
        prolific_maker=prolific,
    )


def format_makers_cell(makers: list[dict]) -> str:
    """
    Show Maker *name* as the link label.
    If name is missing, fallback to @username.
    Link uses makers.url, fallback to https://www.producthunt.com/@username
    """
    if not makers:
        return "—"

    out = []
    for m in makers:
        username = (m.get("username") or "").strip()
        name = md_escape(m.get("name") or "")
        url = (m.get("url") or "").strip()

        if not url and username:
            url = f"https://www.producthunt.com/@{username}"

        label = name or (f"@{username}" if username else "maker")

        # Optional: show both name and @username
        if name and username:
            label = f"{name} (@{username})"

        out.append(safe_link(label, url))

    return ", ".join(out)


def render_posts_table(posts: list[dict]) -> str:
    lines = []
    lines.append("| # | App | Tagline | Maker(s) | Votes |")
    lines.append("|---:|---|---|---|---:|")

    posts_sorted = sorted(posts, key=lambda p: int(p.get("votesCount") or 0), reverse=True)

    for i, p in enumerate(posts_sorted, 1):
        name = md_escape(p.get("name") or "")
        tagline = md_escape(p.get("tagline") or "")
        url = (p.get("url") or "").strip()
        votes = int(p.get("votesCount") or 0)

        makers_cell = format_makers_cell(p.get("makers") or [])
        app_cell = safe_link(name, url) if url else name

        lines.append(f"| {i} | {app_cell} | {tagline} | {makers_cell} | {votes} |")

    return "\n".join(lines) + "\n"


def build_daily_report_md(
    tz_name: str,
    label_dd_mm_yyyy: str,
    stats: DailyStats,
    posts: list[dict],
    rel_link_to_today: str,
) -> str:
    header = f"# Product Hunt — launches for {label_dd_mm_yyyy}\n"
    sub = f"_Timezone for “today”: `{tz_name}`. Source: Product Hunt API._\n\n"

    summary = []
    summary.append("## Summary\n")
    summary.append(f"- Launches: **{stats.count}**")
    summary.append(f"- Total votes: **{stats.total_votes}**")
    summary.append(f"- Avg votes: **{stats.avg_votes:.2f}**")
    summary.append(f"- Median votes: **{stats.median_votes:.2f}**")
    summary.append(f"- Unique makers: **{stats.unique_makers}**")
    summary.append(f"- Most prolific maker: **{md_escape(stats.prolific_maker)}**")
    summary.append(f"- Report file: {safe_link(label_dd_mm_yyyy, rel_link_to_today)}")
    summary.append("\n")

    top_block = []
    top_block.append("## Launches (sorted by votes)\n")
    top_block.append(render_posts_table(posts))

    return header + sub + "\n".join(summary) + "\n" + "\n".join(top_block)


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
    """
    Build <details> navigation over YYYY/MM/*.md
    """
    years = []
    for entry in os.listdir("."):
        if entry.isdigit() and len(entry) == 4 and os.path.isdir(entry):
            years.append(entry)
    years.sort(reverse=True)

    if not years:
        return "_No reports yet._"

    lines = []
    for y in years:
        months = []
        for m in os.listdir(y):
            if m.isdigit() and len(m) == 2 and os.path.isdir(os.path.join(y, m)):
                months.append(m)
        months.sort(reverse=True)

        lines.append("<details>")
        lines.append(f"<summary>{y}</summary>\n")

        if not months:
            lines.append("_Empty_\n")
            lines.append("</details>\n")
            continue

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


def build_today_readme_block(
    tz_name: str,
    label_dd_mm_yyyy: str,
    stats: DailyStats,
    posts: list[dict],
    rel_link_to_today: str,
) -> str:
    lines = []
    lines.append(f"### {label_dd_mm_yyyy} ({tz_name})\n")
    lines.append(f"- Launches: **{stats.count}**")
    lines.append(f"- Total votes: **{stats.total_votes}**")
    lines.append(f"- Avg / Median votes: **{stats.avg_votes:.2f} / {stats.median_votes:.2f}**")
    lines.append(f"- Unique makers: **{stats.unique_makers}**")
    lines.append(f"- Most prolific maker: **{md_escape(stats.prolific_maker)}**")
    lines.append(f"- Full report: {safe_link(label_dd_mm_yyyy, rel_link_to_today)}\n")
    lines.append(render_posts_table(posts))
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    token = (os.getenv("PRODUCTHUNT_TOKEN") or "").strip()
    if not token:
        print("Missing env PRODUCTHUNT_TOKEN", file=sys.stderr)
        return 2

    tz_name = (os.getenv("PH_TZ") or "Europe/Helsinki").strip() or "Europe/Helsinki"
    top_n = int((os.getenv("TOP_N") or "10").strip() or "10")

    start_local, end_local, label, year, month = get_target_day(tz_name)

    posts = fetch_posts_for_day(token, start_local, end_local)
    stats = compute_daily_stats(posts, top_n=top_n)

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
