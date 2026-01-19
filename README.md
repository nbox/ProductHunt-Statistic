# ProductHunt-Statistic

A public, auto-updated catalog of **Product Hunt launches** with simple **daily stats**.

This repository automatically:
- fetches launches for **today** (based on a configured timezone),
- creates/updates a daily markdown report in `YYYY/MM/DD-MM-YYYY.md`,
- updates this `README.md` with:
  - a “Today” summary + table,
  - an archive navigation (expandable by year and month).

## Archive

<!-- START:ARCHIVE -->
<details>
<summary>2026</summary>

  <details>
  <summary>01</summary>

  - [20-01-2026](2026/01/20-01-2026.md)

  </details>

</details>

<!-- END:ARCHIVE -->

## Today

<!-- START:PH_TODAY -->
### 20-01-2026 (Europe/Helsinki)

- Launches: **0**
- Total votes: **0**
- Avg / Median votes: **0.00 / 0.00**
- Unique makers: **0**
- Most prolific maker: **—**
- Full report: [20-01-2026](<2026/01/20-01-2026.md>)

| # | App | Tagline | Maker(s) | Votes |
|---:|---|---|---|---:|

<!-- END:PH_TODAY -->


## Setup

1) Create a **Developer Token** in Product Hunt.
2) Add it to your GitHub repository secrets:

**Settings → Secrets and variables → Actions → New repository secret**
- Name: `PRODUCTHUNT_TOKEN`
- Value: `<your developer token>`

Optional environment variables (used by the workflow):
- `PH_TZ` (default: `Europe/Helsinki`)
- `TOP_N` (default: `10`)
- `DATE` (optional manual override: `YYYY-MM-DD`)


## Local run (optional)

```bash
export PRODUCTHUNT_TOKEN="..."
export PH_TZ="Europe/Helsinki"
python3 scripts/update_catalog.py
