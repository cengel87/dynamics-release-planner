# 🚀 D365 & Power Platform Release Tracker — Team Edition

A collaborative internal tool for tracking Microsoft Dynamics 365 and Power Platform release features, built with Streamlit and backed by Supabase.

## Features

### Core Dashboard
- **Live data** from Microsoft's Release Plans API with pagination support
- **Status derived from dates**: Generally Available, Public Preview, Early Access, Planned
- **6 tabs**: Overview, All Features, Enablement, Watchlist, Changes, By Status
- **Rich filtering**: Product, Status, Wave, Investment Area, Enabled For, GA Date Range, Search
- **Feature cards** with business value, details, dates, and action buttons

### Collaboration (requires Supabase)
- **Watchlist**: Star features to track; see all watched features in one place
- **Team Notes**: Add notes/comments per feature; visible to all team members
- **Saved Views**: Save filter combinations; share views with the team
- **Change Detection**: Detect date shifts, description updates, new features; badges on changed items
- **Change Log**: Full audit trail of every detected change with old/new values

### Authentication
- Simple username/password auth stored in Supabase
- Team member registration
- Role-based (admin/member) — extensible

## Architecture

```
┌─────────────────────────┐     ┌──────────────────────┐
│  Streamlit Cloud        │────▶│  Microsoft API       │
│  (free private apps)    │     │  releaseplans.       │
│                         │     │  microsoft.com       │
│  app.py (single file)   │     └──────────────────────┘
│                         │
│                         │     ┌──────────────────────┐
│                         │────▶│  Supabase            │
│                         │     │  (free Postgres)     │
│                         │     │  - users             │
│                         │     │  - watchlist          │
│                         │     │  - notes             │
│                         │     │  - saved_views       │
│                         │     │  - feature_snapshots  │
│                         │     │  - change_log        │
│                         │     │  - refresh_log       │
└─────────────────────────┘     └──────────────────────┘
```

## Quick Start

### 1. Set Up Supabase (Free Tier)

1. Create a project at [supabase.com](https://supabase.com)
2. Go to **SQL Editor** and paste the contents of `supabase_setup.sql`
3. Click **Run** to create all tables
4. Go to **Settings > API** and copy:
   - Project URL (e.g., `https://abc123.supabase.co`)
   - `service_role` key (NOT the anon key)

### 2. Deploy to Streamlit Cloud

1. Push this repo to GitHub (private repo recommended)
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Click **New app** → select your repo → set `app.py` as the main file
4. Go to **App Settings > Secrets** and add:

```toml
[supabase]
url = "https://your-project.supabase.co"
key = "your-service-role-key"
```

5. Deploy! The app auto-deploys on every `git push`.

### 3. First Login

The SQL setup creates a default admin user:
- **Username**: `admin`
- **Password**: `admin123`

⚠️ **Change this immediately** after first login by registering a new admin account.

### 4. Local Development

```bash
# Clone the repo
git clone <your-repo-url>
cd release-tracker

# Install dependencies
pip install -r requirements.txt

# Copy secrets template
cp secrets.toml.example .streamlit/secrets.toml
# Edit .streamlit/secrets.toml with your Supabase credentials

# (Optional) Place a local copy of the data for offline dev
# Download from https://releaseplans.microsoft.com/en-US/allreleaseplans/
# Save as releaseplans.json in the project root

# Run
streamlit run app.py
```

## Demo Mode

The app works **without Supabase** in demo mode:
- All data viewing, filtering, and analysis works
- Watchlist, notes, saved views, and change detection are disabled
- No login required

This is useful for quick demos or when Supabase is unavailable.

## Data Refresh & Change Detection

### Manual Refresh
Click **🔄 Refresh & Detect Changes** in the header. This:
1. Fetches fresh data from Microsoft's API
2. Compares each feature against the last stored snapshot
3. Logs any changes (date shifts, description updates, etc.)
4. Updates the change log and badges

### Automatic Refresh
The data is cached for 4 hours (`ttl=3600*4`). After the cache expires, the next page load triggers a fresh fetch. Change detection only runs when you explicitly click the refresh button.

### What's Tracked
- GA date, Preview date, Early Access date changes
- Release Wave changes
- Business value and Feature details text changes
- Enabled for changes
- New features appearing in the API
- Investment area changes

## File Structure

```
release-tracker/
├── .streamlit/
│   └── config.toml          # Streamlit theme config
├── app.py                    # Main application (single file!)
├── requirements.txt          # Python dependencies
├── supabase_setup.sql        # Database schema (run in Supabase SQL Editor)
├── secrets.toml.example      # Secrets template
├── releaseplans.json         # (optional) Local data fallback
└── README.md                 # This file
```

## Customization

### Default Products Filter
Edit the `sel_product` default in the sidebar section of `app.py` to change which products are selected by default.

### Cache Duration
Change `ttl=3600 * 4` in `@st.cache_data` decorators to adjust how long data is cached.

### Status Colors
Edit `STATUS_COLORS` dict at the top of `app.py`.

### Adding New Change Types
Add to `TRACKED_FIELDS` list and `CHANGE_TYPE_LABELS` dict.

## API Reference

The app uses Microsoft's undocumented but public API:
- **All plans**: `https://releaseplans.microsoft.com/en-US/allreleaseplans/`
- **Pagination**: `?page=N` when `morerecords: true`
- **Returns**: JSON with `totalrecords`, `morerecords`, `results[]`

Each feature includes: Product name, Feature name, Investment area, Business value, Feature details, Enabled for, Early access date, Public preview date, GA date, Release Plan ID, and more.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Could not load release plan data" | API may be down; place `releaseplans.json` locally as fallback |
| Supabase connection failed | Check secrets.toml; verify service_role key |
| "Only X valid features parsed" | API format may have changed; check response manually |
| Slow initial load | First load fetches ~1200+ features; subsequent loads use cache |
| Changes not detected | Must click "Refresh & Detect Changes" explicitly |

## License

Internal tool — adapt as needed for your organization.
