"""
Dynamics 365 & Power Platform Release Tracker
==============================================

A Streamlit app for tracking Microsoft D365 and Power Platform release features.

Features:
- Live data from Microsoft's Release Planner API
- 4 focused tabs: Overview, By Status, All Features, Recent Updates
- Status derived from dates (Early Access, Public Preview, Generally Available, Planned)
- Future-focused: shows upcoming releases, not historical data
- Microsoft terminology throughout (no custom "shipped" status)
- Early Access prominently featured

Data Source: https://releaseplans.microsoft.com/en-US/allreleaseplans/
"""

import json
import re
import requests
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from urllib.parse import quote_plus
import urllib.parse

# ────────────────────────────────────────────────
# CONFIG
# ────────────────────────────────────────────────

URL = "https://releaseplans.microsoft.com/en-US/allreleaseplans/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 "
                  "Streamlit-D365ReleaseDashboard/2026.2",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

# Status color mapping for consistent UI (Microsoft terminology)
STATUS_COLORS = {
    "Generally Available": "#28a745",   # Green
    "Public Preview": "#17a2b8",        # Blue
    "Early Access": "#9467bd",          # Purple
    "Planned": "#6c757d",               # Gray
}

# ────────────────────────────────────────────────
# RELEASE WAVE REFERENCE
# ────────────────────────────────────────────────
# Based on Microsoft documentation:
# - Wave 1: April 1 GA, features release April-September
# - Wave 2: October 1 GA, features release October-March
# Regional deployment happens over several weeks after GA date

RELEASE_WAVES = {
    "2024 release wave 1": {"ga_start": "2024-04-01", "feature_end": "2024-09-30"},
    "2024 release wave 2": {"ga_start": "2024-10-01", "feature_end": "2025-03-31"},
    "2025 release wave 1": {"ga_start": "2025-04-01", "feature_end": "2025-09-30"},
    "2025 release wave 2": {"ga_start": "2025-10-01", "feature_end": "2026-03-31"},
    "2026 release wave 1": {"ga_start": "2026-04-01", "feature_end": "2026-09-30"},
    "2026 release wave 2": {"ga_start": "2026-10-01", "feature_end": "2027-03-31"},
}

# ────────────────────────────────────────────────
# DATA FETCH & PARSE
# ────────────────────────────────────────────────

@st.cache_data(ttl=3600 * 4, show_spinner="Fetching latest release plans…")
def fetch_release_plans():
    """
    Fetch and parse release plans from Microsoft's API.
    Uses raw JSON field names as provided by Microsoft.
    Status is determined ONLY from dates - there is no status field in the JSON.
    """
    try:
        resp = requests.get(URL, headers=HEADERS, timeout=90)
        resp.raise_for_status()
        raw_text = resp.text.strip()

        features = []

        # Extract JSON array from response
        wrapper_match = re.search(
            r'\{[^}]*"totalrecords"\s*:\s*"[^"]+"[^}]*"results"\s*:\s*\[\s*(.+?)\s*\]\s*\}',
            raw_text, re.DOTALL | re.MULTILINE
        )
        if wrapper_match:
            array_str = re.sub(r',\s*$', '', wrapper_match.group(1).strip())
            object_strings = re.findall(r'\s*(\{.+?\})\s*(?:,|$)', array_str, re.DOTALL)
            for obj_str in object_strings:
                obj_str = obj_str.strip()
                if obj_str.count('"') % 2 != 0:
                    obj_str += '"'
                obj_str = re.sub(r',\s*}', '}', obj_str)
                try:
                    f = json.loads(obj_str)
                    if isinstance(f, dict) and "Feature name" in f:
                        features.append(f)
                except Exception:
                    pass

        if len(features) < 100:
            st.error(f"Only {len(features)} valid features parsed — site format may have changed.")
            return None

        def clean(val):
            """Remove HTML tags and clean text"""
            if not val:
                return ""
            return BeautifulSoup(str(val), "html.parser").get_text(" ", strip=True)

        def parse_date(val):
            """Parse date strings to pandas datetime"""
            if not val or val in ("", "N/A", "TBD"):
                return pd.NaT
            try:
                return pd.to_datetime(val, errors="coerce")
            except:
                return pd.NaT

        today = pd.Timestamp.now().normalize()
        rows = []

        for f in features:
            # Parse all dates from Microsoft's JSON
            early_access = parse_date(f.get("Early access date"))
            preview = parse_date(f.get("Public preview date"))
            ga = parse_date(f.get("GA date"))
            last_updated = parse_date(f.get("Last Gitcommit date"))
            
            # Determine status based ONLY on dates (no status field exists in JSON)
            # Using Microsoft terminology: Generally Available, Public Preview, Early Access, Planned
            status = "Planned"
            
            if pd.notna(ga) and ga <= today:
                status = "Generally Available"
            elif pd.notna(preview) and preview <= today:
                status = "Public Preview"
            elif pd.notna(early_access) and early_access <= today:
                status = "Early Access"
            
            # Calculate days metrics
            days_to_ga = (ga - today).days if pd.notna(ga) else None
            days_in_preview = (ga - preview).days if pd.notna(ga) and pd.notna(preview) else None
            
            # Build row using Microsoft's exact field names from JSON
            rows.append({
                # Core identification (verbatim from JSON)
                "Product name": clean(f.get("Product name")),
                "Feature name": clean(f.get("Feature name")),
                "Release Plan ID": str(f.get("Release Plan ID", "")),
                
                # Dates (verbatim from JSON)
                "Early access date": early_access,
                "Public preview date": preview,
                "GA date": ga,
                
                # Release waves (verbatim from JSON)
                "Public Preview Release Wave": str(f.get("Public Preview Release Wave", "")).strip(),
                "GA Release Wave": str(f.get("GA Release Wave", "")).strip(),
                
                # Additional info (verbatim from JSON)
                "Investment area": clean(f.get("Investment area")),
                "Business value": clean(f.get("Business value")),
                "Feature details": clean(f.get("Feature details")),
                "Enabled for": clean(f.get("Enabled for")),
                
                # Metadata (verbatim from JSON)
                "Last Gitcommit date": last_updated,
                
                # Calculated fields (not in JSON, derived from dates)
                "Status": status,  # Derived from dates
                "Days to GA": days_to_ga,
                "Days in Preview": days_in_preview,
            })

        df = pd.DataFrame(rows)
        
        # Clean up empty values
        df = df.replace({"": None, "None": None})
        
        # Create combined release wave for convenience
        df["Release Wave"] = df["GA Release Wave"].where(
            df["GA Release Wave"].notna() & (df["GA Release Wave"] != ""), 
            df["Public Preview Release Wave"]
        )
        
        # Sort by last updated
        df = df.sort_values("Last Gitcommit date", ascending=False, na_position="last")
        
        # Create release planner search links
        def create_search_link(row):
            product = row.get("Product name", "")
            feature = row.get("Feature name", "")
            
            # Simplify product name for app parameter
            # Remove "Dynamics 365" and "Microsoft" prefixes
            app_name = product.replace("Dynamics 365 ", "").replace("Microsoft ", "").strip()
            
            # Build URL
            base_url = "https://releaseplans.microsoft.com/en-us/"
            params = f"?app={urllib.parse.quote(app_name)}&q={urllib.parse.quote(feature)}"
            return base_url + params
        
        df["Search Link"] = df.apply(create_search_link, axis=1)
        
        return df

    except Exception as e:
        st.error(f"Error loading data: {e}")
        import traceback
        st.code(traceback.format_exc())
        return None

# ────────────────────────────────────────────────
# ANALYTICS FUNCTIONS
# ────────────────────────────────────────────────

def get_status_summary(df):
    """Get counts by status with color coding"""
    status_counts = df["Status"].value_counts()
    return status_counts

def get_upcoming_releases(df, days=90):
    """Get features releasing in the next N days"""
    today = pd.Timestamp.now().normalize()
    future_date = today + timedelta(days=days)
    
    upcoming = df[
        (df["GA date"].notna()) & 
        (df["GA date"] > today) & 
        (df["GA date"] <= future_date)
    ].copy()
    
    return upcoming.sort_values("GA date")


# ────────────────────────────────────────────────
# STREAMLIT APP
# ────────────────────────────────────────────────

st.set_page_config(
    page_title="D365 & Power Platform Release Tracker",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🚀 Dynamics 365 & Power Platform Release Tracker")
st.caption(f"Last Refreshed: {datetime.utcnow():%Y-%m-%d %H:%M UTC}")

# Info about status determination
with st.expander("ℹ️ How Status is Determined"):
    st.markdown("""
    **Status is calculated from dates only** (Microsoft's API doesn't provide a status field):
    
    - **Generally Available**: GA date has passed
    - **Public Preview**: Preview date has passed (no GA date yet or not reached)
    - **Early Access**: Early access date has passed (no preview/GA yet or not reached)
    - **Planned**: Has release wave but dates haven't occurred yet
    
    ⚠️ **Important**: Regional rollout timing varies. A feature marked "Generally Available" here 
    means its GA date passed, but actual availability depends on your region, environment, and admin settings.
    See [deployment schedule](https://learn.microsoft.com/en-us/power-platform/admin/general-availability-deployment).
    """)

# Refresh button
col1, col2 = st.columns([6, 1])
with col2:
    if st.button("↻ Refresh", type="primary", use_container_width=True):
        fetch_release_plans.clear()
        st.rerun()

# Load data
df = fetch_release_plans()
if df is None or df.empty:
    st.stop()

# ── Sidebar Filters ──────────────────────────────
with st.sidebar:
    st.header("🔍 Filters")
    
    # Search
    search = st.text_input("🔎 Search", placeholder="Keywords...", label_visibility="collapsed")
    
    if search:
        st.caption(f"Searching for: {search}")
    
    st.divider()

    # Product filter
    sel_product = st.multiselect(
        "Product",
        options=sorted(df["Product name"].dropna().unique()),
        default=[
            "Dynamics 365 Field Service",
            "Power Apps",
            "Power Automate",
            "Microsoft Power Platform governance and administration",
            "Microsoft Dataverse"
        ]
    )

    # Status filter (calculated from dates)
    sel_status = st.multiselect(
        "Status",
        options=["Generally Available", "Public Preview", "Early Access", "Planned"],
        default=[]
    )

    # Release wave filter
    sel_wave = st.multiselect(
        "Release Wave",
        options=sorted([w for w in df["Release Wave"].dropna().unique()]),
        default=[]
    )

    # Investment area filter
    sel_area = st.multiselect(
        "Investment Area",
        options=sorted(df["Investment area"].dropna().unique()),
        default=[]
    )

    # Date range filter
    use_date_filter = st.checkbox("Filter by GA Date")
    
    if use_date_filter:
        date_col = st.columns(2)
        with date_col[0]:
            start_date = st.date_input(
                "From",
                value=pd.Timestamp.now().date(),
                key="start_date"
            )
        with date_col[1]:
            end_date = st.date_input(
                "To",
                value=(pd.Timestamp.now() + timedelta(days=180)).date(),
                key="end_date"
            )

# Apply filters
filtered = df.copy()

if sel_product:
    filtered = filtered[filtered["Product name"].isin(sel_product)]

if sel_status:
    filtered = filtered[filtered["Status"].isin(sel_status)]

if sel_wave:
    filtered = filtered[filtered["Release Wave"].isin(sel_wave)]

if sel_area:
    filtered = filtered[filtered["Investment area"].isin(sel_area)]

if use_date_filter:
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    filtered = filtered[
        (filtered["GA date"].notna()) & 
        (filtered["GA date"] >= start) & 
        (filtered["GA date"] <= end)
    ]

if search:
    s = search.lower()
    mask = (
        filtered["Feature name"].str.lower().str.contains(s, na=False) |
        filtered["Business value"].str.lower().str.contains(s, na=False) |
        filtered["Feature details"].str.lower().str.contains(s, na=False) |
        filtered["Investment area"].str.lower().str.contains(s, na=False) |
        filtered["Product name"].str.lower().str.contains(s, na=False)
    )
    filtered = filtered[mask]

# ── Key Metrics ──────────────────────────────────
st.markdown(f"### 📊 Overview: {len(filtered):,} of {len(df):,} features")

metric_cols = st.columns(6)

# Status breakdown using Microsoft terminology
status_counts = get_status_summary(filtered)

statuses = ["Generally Available", "Public Preview", "Early Access", "Planned"]
colors = ["🟢", "🔵", "🟣", "⚪"]

for i, (status, color) in enumerate(zip(statuses, colors)):
    count = status_counts.get(status, 0)
    pct = (count / len(filtered) * 100) if len(filtered) > 0 else 0
    metric_cols[i].metric(
        f"{color} {status}",
        f"{count:,}",
        f"{pct:.1f}%"
    )

# Upcoming releases
upcoming_30 = len(filtered[
    (filtered["Days to GA"].notna()) & 
    (filtered["Days to GA"] >= 0) & 
    (filtered["Days to GA"] <= 30)
])
metric_cols[4].metric("🎯 GA in 30d", upcoming_30)

# With dates
with_dates = len(filtered[
    (filtered["GA date"].notna()) | 
    (filtered["Public preview date"].notna()) | 
    (filtered["Early access date"].notna())
])
metric_cols[5].metric("📅 Dated", with_dates)

st.divider()

# ── Main Tabs ────────────────────────────────────
tab_overview, tab_enablement, tab_status, tab_table, tab_recent = st.tabs([
    "📈 Overview",
    "⚙️ Enablement",
    "📊 By Status",
    "📋 All Features",
    "🆕 Recent Updates"
])

# ── OVERVIEW ─────────────────────────────────────
with tab_overview:
    st.subheader("Release Pipeline")
    
    overview_cols = st.columns([2, 1])
    
    with overview_cols[0]:
        # Upcoming releases by month
        upcoming_data = filtered[
            (filtered["GA date"].notna()) & 
            (filtered["GA date"] >= pd.Timestamp.now().normalize())
        ].copy()
        
        if not upcoming_data.empty:
            upcoming_data["Month"] = upcoming_data["GA date"].dt.to_period("M").astype(str)
            monthly_upcoming = upcoming_data.groupby(["Month", "Status"]).size().reset_index(name="Count")
            
            fig_upcoming = px.bar(
                monthly_upcoming,
                x="Month",
                y="Count",
                color="Status",
                title="Upcoming Releases by Month",
                height=400,
                color_discrete_map=STATUS_COLORS,
                barmode="stack"
            )
            st.plotly_chart(fig_upcoming, use_container_width=True)
        else:
            st.info("No upcoming releases with GA dates")
    
    with overview_cols[1]:
        # Status pie
        status_dist = filtered["Status"].value_counts().reset_index()
        status_dist.columns = ["Status", "Count"]
        
        fig_pie = px.pie(
            status_dist,
            values="Count",
            names="Status",
            title="Current Status",
            height=400,
            color="Status",
            color_discrete_map=STATUS_COLORS
        )
        st.plotly_chart(fig_pie, use_container_width=True)
    
    st.divider()
    st.subheader("Next 90 Days")
    
    upcoming = get_upcoming_releases(filtered, days=90)
    
    if not upcoming.empty:
        upcoming["Month"] = upcoming["GA date"].dt.strftime("%Y-%m (%B)")
        monthly_upcoming = upcoming.groupby(["Month", "Product name"]).size().reset_index(name="Count")
        
        fig_upcoming_product = px.bar(
            monthly_upcoming,
            x="Month",
            y="Count",
            color="Product name",
            title="Planned GA by Product",
            height=400,
            text="Count"
        )
        fig_upcoming_product.update_traces(textposition="outside")
        st.plotly_chart(fig_upcoming_product, use_container_width=True)
        
        with st.expander(f"📋 View {len(upcoming)} Upcoming Features"):
            st.dataframe(
                upcoming[["Product name", "Feature name", "GA date", "Days to GA", "Status", "Release Wave"]],
                use_container_width=True,
                hide_index=True
            )
    else:
        st.info("No releases scheduled in the next 90 days")

# ── ENABLEMENT ANALYSIS ──────────────────────────
with tab_enablement:
    st.subheader("⚙️ Feature Enablement Analysis")
    
    st.info("""
    **Microsoft's Enablement Categories:**
    - **Users, automatically** - Deploys immediately when GA date passes, affects all users
    - **Admins, makers, marketers, or analysts, automatically** - Auto-deploys for these roles
    - **Users by admins, makers, or analysts** - Requires manual enablement by admin/maker
    """)
    
    # Get exact enablement categories from Microsoft
    enablement_categories = filtered["Enabled for"].fillna("Not specified").unique()
    
    # Create tabs for each category
    enablement_tabs = st.tabs([
        "🔴 Users, automatically",
        "🟠 Admins/makers, automatically", 
        "🟡 Users by admins/makers",
        "⚪ Not specified"
    ])
    
    # Tab 1: Users, automatically
    with enablement_tabs[0]:
        st.markdown("### Auto-Enabled for All Users")
        st.warning("⚠️ These features deploy automatically when GA date passes. They affect all users without admin action.")
        
        auto_users = filtered[filtered["Enabled for"] == "Users, automatically"].copy()
        
        if not auto_users.empty:
            st.metric("Total Features", len(auto_users))
            
            # Upcoming vs Already deployed
            upcoming_auto = auto_users[
                (auto_users["GA date"].notna()) & 
                (auto_users["GA date"] >= pd.Timestamp.now().normalize())
            ].sort_values("GA date")
            
            already_auto = auto_users[
                (auto_users["GA date"].notna()) & 
                (auto_users["GA date"] < pd.Timestamp.now().normalize())
            ]
            
            cols = st.columns(2)
            cols[0].metric("Coming Soon", len(upcoming_auto), "📅 Not deployed yet")
            cols[1].metric("Already Deployed", len(already_auto), "✅ Live now")
            
            if not upcoming_auto.empty:
                st.markdown("#### 🚨 Upcoming Auto-Enabled Features")
                
                # Timeline by month
                upcoming_auto["Month"] = upcoming_auto["GA date"].dt.strftime("%Y-%m")
                monthly = upcoming_auto.groupby("Month").size().reset_index(name="Count")
                
                fig = px.bar(
                    monthly,
                    x="Month",
                    y="Count",
                    title="Auto-Enabled Features by Month",
                    color_discrete_sequence=["#dc3545"]
                )
                st.plotly_chart(fig, use_container_width=True)
                
                st.dataframe(
                    upcoming_auto[[
                        "Product name", "Feature name", "GA date", "Days to GA", 
                        "Status", "Release Wave", "Search Link"
                    ]],
                    column_config={
                        "GA date": st.column_config.DateColumn("GA Date", format="YYYY-MM-DD"),
                        "Days to GA": st.column_config.NumberColumn("Days Until GA", format="%d"),
                        "Search Link": st.column_config.LinkColumn("Search", display_text="🔍"),
                    },
                    use_container_width=True,
                    hide_index=True
                )
                
                st.download_button(
                    "📥 Download CSV",
                    upcoming_auto.to_csv(index=False),
                    file_name=f"users_auto_{datetime.now():%Y%m%d}.csv",
                    mime="text/csv"
                )
            
            if not already_auto.empty:
                with st.expander(f"📋 {len(already_auto)} Already Deployed"):
                    st.dataframe(
                        already_auto[[
                            "Product name", "Feature name", "GA date", 
                            "Status", "Release Wave", "Search Link"
                        ]],
                        column_config={
                            "GA date": st.column_config.DateColumn("GA Date", format="YYYY-MM-DD"),
                            "Search Link": st.column_config.LinkColumn("Search", display_text="🔍"),
                        },
                        use_container_width=True,
                        hide_index=True
                    )
        else:
            st.success("✅ No auto-enabled features in current filters")
    
    # Tab 2: Admins, makers, marketers, or analysts, automatically
    with enablement_tabs[1]:
        st.markdown("### Auto-Enabled for Admins/Makers/Marketers/Analysts")
        st.info("ℹ️ These features auto-deploy but only affect admin, maker, marketer, and analyst roles.")
        
        auto_admins = filtered[
            filtered["Enabled for"] == "Admins, makers, marketers, or analysts, automatically"
        ].copy()
        
        if not auto_admins.empty:
            st.metric("Total Features", len(auto_admins))
            
            upcoming = auto_admins[
                (auto_admins["GA date"].notna()) & 
                (auto_admins["GA date"] >= pd.Timestamp.now().normalize())
            ].sort_values("GA date")
            
            if not upcoming.empty:
                st.dataframe(
                    upcoming[[
                        "Product name", "Feature name", "GA date", "Days to GA",
                        "Status", "Release Wave", "Search Link"
                    ]],
                    column_config={
                        "GA date": st.column_config.DateColumn("GA Date", format="YYYY-MM-DD"),
                        "Days to GA": st.column_config.NumberColumn("Days Until GA", format="%d"),
                        "Search Link": st.column_config.LinkColumn("Search", display_text="🔍"),
                    },
                    use_container_width=True,
                    hide_index=True
                )
        else:
            st.info("No features in this category for current filters")
    
    # Tab 3: Users by admins, makers, or analysts
    with enablement_tabs[2]:
        st.markdown("### Admin-Controlled Enablement")
        st.success("✅ You control when these features are enabled. They deploy but remain hidden until you enable them.")
        
        admin_controlled = filtered[
            filtered["Enabled for"] == "Users by admins, makers, or analysts"
        ].copy()
        
        if not admin_controlled.empty:
            st.metric("Total Features", len(admin_controlled))
            
            # Available now vs Coming soon
            available = admin_controlled[admin_controlled["Status"] == "Generally Available"]
            coming = admin_controlled[admin_controlled["Status"] != "Generally Available"]
            
            cols = st.columns(2)
            cols[0].metric("Available to Enable", len(available))
            cols[1].metric("Coming Soon", len(coming))
            
            if not available.empty:
                st.markdown("#### Available for Enablement")
                st.dataframe(
                    available[[
                        "Product name", "Feature name", "GA date",
                        "Status", "Release Wave", "Search Link"
                    ]],
                    column_config={
                        "GA date": st.column_config.DateColumn("GA Date", format="YYYY-MM-DD"),
                        "Search Link": st.column_config.LinkColumn("Search", display_text="🔍"),
                    },
                    use_container_width=True,
                    hide_index=True,
                    height=400
                )
            
            if not coming.empty:
                with st.expander(f"🔜 {len(coming)} Features Coming Soon"):
                    st.dataframe(
                        coming[[
                            "Product name", "Feature name", "GA date", "Days to GA",
                            "Status", "Release Wave", "Search Link"
                        ]],
                        column_config={
                            "GA date": st.column_config.DateColumn("GA Date", format="YYYY-MM-DD"),
                            "Days to GA": st.column_config.NumberColumn("Days Until GA", format="%d"),
                            "Search Link": st.column_config.LinkColumn("Search", display_text="🔍"),
                        },
                        use_container_width=True,
                        hide_index=True
                    )
        else:
            st.info("No admin-controlled features in current filters")
    
    # Tab 4: Not specified
    with enablement_tabs[3]:
        st.markdown("### Enablement Not Specified")
        st.info("ℹ️ Microsoft hasn't specified how these features are enabled. Check documentation.")
        
        not_specified = filtered[filtered["Enabled for"].isna()]
        
        if not not_specified.empty:
            st.metric("Total Features", len(not_specified))
            
            st.dataframe(
                not_specified[[
                    "Product name", "Feature name", "GA date",
                    "Status", "Release Wave", "Search Link"
                ]],
                column_config={
                    "GA date": st.column_config.DateColumn("GA Date", format="YYYY-MM-DD"),
                    "Search Link": st.column_config.LinkColumn("Search", display_text="🔍"),
                },
                use_container_width=True,
                hide_index=True
            )
        else:
            st.success("All features have specified enablement methods")
    
    st.divider()
    
    # Summary chart
    st.subheader("Enablement Distribution")
    
    enablement_summary = filtered["Enabled for"].fillna("Not specified").value_counts().reset_index()
    enablement_summary.columns = ["Enablement Type", "Count"]
    
    # Simplify labels for chart
    enablement_summary["Category"] = enablement_summary["Enablement Type"].apply(
        lambda x: "🔴 Users, auto" if x == "Users, automatically"
        else ("🟠 Admins, auto" if x == "Admins, makers, marketers, or analysts, automatically"
        else ("🟡 By admins" if x == "Users by admins, makers, or analysts"
        else "⚪ Not specified"))
    )
    
    fig_summary = px.pie(
        enablement_summary,
        values="Count",
        names="Category",
        title="Features by Enablement Type",
        color="Category",
        color_discrete_map={
            "🔴 Users, auto": "#dc3545",
            "🟠 Admins, auto": "#fd7e14",
            "🟡 By admins": "#ffc107",
            "⚪ Not specified": "#6c757d"
        }
    )
    st.plotly_chart(fig_summary, use_container_width=True)

# ── BY STATUS ────────────────────────────────────
with tab_status:
    st.subheader("Features by Status")
    
    # Status breakdown
    status_cols = st.columns(4)
    
    for i, (status, color) in enumerate(zip(statuses, colors)):
        with status_cols[i]:
            status_features = filtered[filtered["Status"] == status]
            st.markdown(f"### {color} {status}")
            st.metric("Count", len(status_features))
            
            if not status_features.empty:
                with st.expander(f"View {len(status_features)} features"):
                    st.dataframe(
                        status_features[[
                            "Product name", "Feature name", "GA date", 
                            "Public preview date", "Early access date", "Release Wave"
                        ]],
                        column_config={
                            "GA date": st.column_config.DateColumn("GA", format="YYYY-MM-DD"),
                            "Public preview date": st.column_config.DateColumn("Preview", format="YYYY-MM-DD"),
                            "Early access date": st.column_config.DateColumn("Early Access", format="YYYY-MM-DD"),
                        },
                        use_container_width=True,
                        hide_index=True,
                        height=300
                    )
    
    st.divider()
    
    # Status by product
    st.subheader("Status Distribution by Product")
    
    status_by_product = filtered.groupby(["Product name", "Status"]).size().reset_index(name="Count")
    
    if not status_by_product.empty:
        fig_status = px.bar(
            status_by_product,
            x="Product name",
            y="Count",
            color="Status",
            title="Features by Product & Status",
            height=500,
            color_discrete_map=STATUS_COLORS,
            barmode="stack"
        )
        st.plotly_chart(fig_status, use_container_width=True)
    
    st.divider()
    
    # Early Access Features
    st.subheader("🟣 Early Access Features")
    early_access_features = filtered[filtered["Status"] == "Early Access"]
    
    if not early_access_features.empty:
        st.markdown(f"**{len(early_access_features)} features in early access**")
        st.info("Early access features are available for testing before public preview. See [opt-in guide](https://learn.microsoft.com/en-us/power-platform/admin/opt-in-early-access-updates).")
        
        st.dataframe(
            early_access_features[[
                "Product name", "Feature name", "Early access date", 
                "Public preview date", "GA date", "Release Wave", "Search Link"
            ]],
            column_config={
                "Early access date": st.column_config.DateColumn("Early Access", format="YYYY-MM-DD"),
                "Public preview date": st.column_config.DateColumn("Preview", format="YYYY-MM-DD"),
                "GA date": st.column_config.DateColumn("GA", format="YYYY-MM-DD"),
                "Search Link": st.column_config.LinkColumn("Search", display_text="🔍"),
            },
            use_container_width=True,
            hide_index=True
        )
        
        st.download_button(
            "📥 Download Early Access Features",
            early_access_features.to_csv(index=False),
            file_name=f"early_access_features_{datetime.now():%Y%m%d}.csv",
            mime="text/csv",
            use_container_width=True
        )
    else:
        st.info("No features currently in early access")

# ── ALL FEATURES TABLE ───────────────────────────
with tab_table:
    st.subheader("All Features")
    
    # Define column order by importance
    display_cols = [
        "Product name",
        "Feature name",
        "Status",
        "GA date",
        "Public preview date",
        "Early access date",
        "GA Release Wave",
        "Public Preview Release Wave",
        "Investment area",
        "Enabled for",
        "Days to GA",
        "Last Gitcommit date",
        "Search Link"
    ]

    event = st.dataframe(
        filtered[display_cols],
        column_config={
            "Product name": st.column_config.TextColumn("Product", width="medium"),
            "Feature name": st.column_config.TextColumn("Feature", width="large"),
            "Status": st.column_config.TextColumn("Status", width="medium"),
            "GA date": st.column_config.DateColumn("GA Date", format="YYYY-MM-DD"),
            "Public preview date": st.column_config.DateColumn("Preview Date", format="YYYY-MM-DD"),
            "Early access date": st.column_config.DateColumn("Early Access", format="YYYY-MM-DD"),
            "GA Release Wave": st.column_config.TextColumn("GA Wave"),
            "Public Preview Release Wave": st.column_config.TextColumn("Preview Wave"),
            "Investment area": st.column_config.TextColumn("Area"),
            "Enabled for": st.column_config.TextColumn("Enabled For"),
            "Days to GA": st.column_config.NumberColumn("Days to GA", format="%d"),
            "Last Gitcommit date": st.column_config.DateColumn("Last Updated", format="YYYY-MM-DD"),
            "Search Link": st.column_config.LinkColumn(
                "Search",
                display_text="🔍",
            ),
        },
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row"
    )

    download_cols = st.columns([1, 1, 2])
    with download_cols[0]:
        st.download_button(
            "📥 Download CSV",
            filtered.to_csv(index=False),
            file_name=f"d365_releases_{datetime.now():%Y%m%d}.csv",
            mime="text/csv",
            use_container_width=True
        )

    # Feature details on selection
    selected = event.selection.get("rows", [])
    if selected:
        row = filtered.iloc[selected[0]]
        st.divider()
        st.subheader(f"📌 {row['Feature name']}")
        
        detail_cols = st.columns(5)
        detail_cols[0].metric("Product", row["Product name"])
        detail_cols[1].metric("Status", row["Status"])
        detail_cols[2].metric("Wave", row["Release Wave"] if pd.notna(row["Release Wave"]) else "TBD")
        detail_cols[3].metric("Area", row["Investment area"] if pd.notna(row["Investment area"]) else "N/A")
        
        # Status indicator
        status_emoji = {
            "Generally Available": "🟢",
            "Public Preview": "🔵",
            "Early Access": "🟣",
            "Planned": "⚪"
        }
        detail_cols[4].metric(status_emoji.get(row["Status"], "⚪"), row["Status"])
        
        if pd.notna(row["Business value"]) and row["Business value"]:
            st.markdown("**💼 Business Value:**")
            st.info(row["Business value"])
        
        if pd.notna(row["Feature details"]) and row["Feature details"]:
            st.markdown("**📝 Details:**")
            st.info(row["Feature details"])
        
        if pd.notna(row["Enabled for"]) and row["Enabled for"]:
            st.markdown(f"**👥 Enabled For:** {row['Enabled for']}")
        
        date_cols = st.columns(4)
        if pd.notna(row["Early access date"]):
            date_cols[0].metric("Early Access", row["Early access date"].strftime("%Y-%m-%d"))
        if pd.notna(row["Public preview date"]):
            date_cols[1].metric("Preview", row["Public preview date"].strftime("%Y-%m-%d"))
        if pd.notna(row["GA date"]):
            date_cols[2].metric("GA Date", row["GA date"].strftime("%Y-%m-%d"))
        if pd.notna(row["Days to GA"]):
            days = int(row["Days to GA"])
            if days > 0:
                date_cols[3].metric("Days Until GA", days)
            elif days < 0:
                date_cols[3].metric("Days Since GA", abs(days))
        
        st.link_button("🔍 Search Google", row["Search Link"], use_container_width=True)


# ── RECENT UPDATES ───────────────────────────────
with tab_recent:
    st.subheader("Recent Updates")
    
    update_period = st.selectbox(
        "Period",
        [("Last 7 Days", 7), ("Last 14 Days", 14), ("Last 30 Days", 30), ("Last 60 Days", 60)],
        format_func=lambda x: x[0]
    )
    
    days = update_period[1]
    today = pd.Timestamp.now()
    recent = filtered[
        (filtered["Last Gitcommit date"].notna()) & 
        ((today - filtered["Last Gitcommit date"]).dt.days <= days)
    ].copy()

    if recent.empty:
        st.info(f"No updates in last {days} days")
    else:
        st.markdown(f"**{len(recent)} features updated**")
        
        recent_by_product = recent.groupby("Product name").size().reset_index(name="Updates")
        recent_by_product = recent_by_product.sort_values("Updates", ascending=False)
        
        fig_recent = px.bar(
            recent_by_product,
            x="Product name",
            y="Updates",
            title=f"Updates by Product (Last {days} Days)",
            height=400,
        )
        st.plotly_chart(fig_recent, use_container_width=True)
        
        st.dataframe(
            recent[display_cols],
            column_config={
                "Search Link": st.column_config.LinkColumn("Search", display_text="🔍"),
                "Last Gitcommit date": st.column_config.DateColumn("Updated", format="YYYY-MM-DD"),
            },
            use_container_width=True,
            hide_index=True
        )

# ── Footer ───────────────────────────────────────
st.divider()
st.caption("Data: Microsoft Dynamics 365 & Power Platform Release Plans | Built with Streamlit")
st.caption("Status calculated from dates. No status field exists in Microsoft's API.")