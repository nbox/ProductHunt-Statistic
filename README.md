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
_No reports yet._
<!-- END:ARCHIVE -->

## Today

<!-- START:PH_TODAY -->
_No data yet. 
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
