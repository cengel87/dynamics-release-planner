# Dynamics 365 & Power Platform Release Tracker

Streamlit dashboard for tracking Microsoft D365 and Power Platform release plans.

## Quick Start

```bash
pip install streamlit pandas plotly requests beautifulsoup4
streamlit run d365_release_tracker_enhanced.py
```

Opens at `http://localhost:8501`

## What It Does

- Pulls live data from Microsoft's Release Planner API
- Shows features by status: Early Access, Public Preview, Generally Available, Planned
- Filters by product, wave, date, area
- Search across all fields

## Tabs

1. **Overview** - Upcoming releases (next 90 days)
2. **By Status** - Features grouped by lifecycle stage
3. **All Features** - Searchable table with all data
4. **Recent Updates** - What changed recently (7/14/30/60 days)

## Key Features

- **Status from dates**: Status calculated from Early Access, Preview, and GA dates
- **Microsoft terminology**: Uses official Microsoft status names
- **Future-focused**: Shows upcoming releases, not historical data
- **Search integration**: Google search link for each feature
- **Export**: Download filtered data as CSV

## Important Notes

- **Status calculation**: Derived from dates (no status field in Microsoft's API)
- **GA ≠ Available**: "Generally Available" means GA date passed, NOT that it's in your environment
- **Regional rollout**: Features deploy over weeks by region
- **Verify in tenant**: Always check your specific environment

## Data Source

`https://releaseplans.microsoft.com/en-US/allreleaseplans/`

Refreshes every 4 hours (manual refresh button available).

## Requirements

- Python 3.8+
- streamlit
- pandas
- plotly
- requests
- beautifulsoup4

---

Not affiliated with Microsoft Corporation.