import json
import re
import requests
import streamlit as st
import pandas as pd
import plotly.express as px
from bs4 import BeautifulSoup
from datetime import datetime

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

# ────────────────────────────────────────────────
# DATA FETCH & PARSE
# ────────────────────────────────────────────────

@st.cache_data(ttl=3600 * 4, show_spinner="Fetching latest release plans…")
def fetch_release_plans():
    try:
        resp = requests.get(URL, headers=HEADERS, timeout=90)
        resp.raise_for_status()
        raw_text = resp.text.strip()

        features = []

        wrapper_match = re.search(
            r'\{[^}]*"totalrecords"\s*:\s*"[^"]+"[^}]*"results"\s*:\s*\[\s*(.+?)\s*\]\s*\}',
            raw_text, re.DOTALL | re.MULTILINE
        )
        if wrapper_match:
            array_str = re.sub(r',\s*$', '', wrapper_match.group(1).strip())
            parsed = json.loads("[" + array_str + "]")
            features.extend([f for f in parsed if isinstance(f, dict) and "Feature name" in f])

        if len(features) < 300:
            st.error(f"Only {len(features)} valid features parsed — site format may have changed.")
            return None

        def clean(val):
            return BeautifulSoup(str(val or ""), "html.parser").get_text(" ", strip=True)

        def parse_date(val):
            if not val or val in ("", "N/A"):
                return pd.NaT
            return pd.to_datetime(val, errors="coerce")

        today = pd.Timestamp.now().normalize()
        rows = []

        for f in features:
            preview = parse_date(f.get("Public preview date"))
            ga = parse_date(f.get("GA date"))
            early = parse_date(f.get("Early access date"))

            status = "Planned"
            if pd.notna(ga) and ga <= today:
                status = "Generally Available"
            elif pd.notna(preview) and preview <= today:
                status = "Public Preview"
            elif pd.notna(early) and early <= today:
                status = "Early Access"

            rows.append({
                "Product": clean(f.get("Product name")),
                "Feature": clean(f.get("Feature name")),
                "Area": clean(f.get("Investment area")),
                "Business Value": clean(f.get("Business value")),
                "Details": clean(f.get("Feature details")),
                "Enabled For": clean(f.get("Enabled for")),
                "Early Access": early,
                "Public Preview": preview,
                "GA": ga,
                "Preview Wave": f.get("Public Preview Release Wave", ""),
                "GA Wave": f.get("GA Release Wave", ""),
                "Status": status,
                "Release Plan ID": f.get("Release Plan ID", ""),
                "Last Updated": f.get("Last Gitcommit date", ""),
            })

        df = pd.DataFrame(rows)
        return df.sort_values("Last Updated", ascending=False, na_position="last")

    except Exception as e:
        st.error(f"Error loading data: {e}")
        return None

# ────────────────────────────────────────────────
# STREAMLIT APP
# ────────────────────────────────────────────────

st.set_page_config(
    page_title="D365 & Power Platform Release Tracker",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("Dynamics 365 & Power Platform Release Plans")
st.caption(f"Refreshed: {datetime.utcnow():%Y-%m-%d %H:%M UTC}")

if st.sidebar.button("↻ Refresh Now", type="primary", use_container_width=True):
    fetch_release_plans.clear()
    st.rerun()

df = fetch_release_plans()
if df is None or df.empty:
    st.stop()

# ── Sidebar Filters ──────────────────────────────
with st.sidebar:
    st.header("Filters")

    sel_product = st.multiselect(
        "Product",
        ["All"] + sorted(df["Product"].dropna().unique()),
        default=["All"]
    )

    sel_status = st.multiselect(
        "Status",
        ["All"] + sorted(df["Status"].unique()),
        default=["All"]
    )

    search = st.text_input("Search")

filtered = df.copy()

if "All" not in sel_product:
    filtered = filtered[filtered["Product"].isin(sel_product)]

if "All" not in sel_status:
    filtered = filtered[filtered["Status"].isin(sel_status)]

if search:
    s = search.lower()
    filtered = filtered[
        filtered["Feature"].str.lower().str.contains(s, na=False) |
        filtered["Business Value"].str.lower().str.contains(s, na=False) |
        filtered["Details"].str.lower().str.contains(s, na=False)
    ]

st.markdown(f"**Showing {len(filtered):,} of {len(df):,} features**")

tab_table, tab_timeline, tab_summary = st.tabs(
    ["📋 Features Table", "📈 Timeline", "📊 Summary"]
)

# ── FEATURES TABLE (UNCHANGED) ───────────────────
with tab_table:
    display_cols = [
        "Product", "Feature", "Status", "Public Preview", "GA",
        "Preview Wave", "GA Wave", "Area", "Enabled For"
    ]

    event = st.dataframe(
        filtered[display_cols],
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row"
    )

    selected = event.selection.get("rows", [])
    if selected:
        row = filtered.iloc[selected[0]]
        st.divider()
        st.subheader(row["Feature"])
        st.markdown(row["Details"] or "—")

# ── TIMELINE (IMPROVED) ──────────────────────────
with tab_timeline:
    st.subheader("Release Timeline")

    group_by = st.selectbox(
        "Group timeline by",
        ["Feature", "Product", "Area"],
        index=1
    )

    timeline_df = filtered.copy()
    timeline_df["Start"] = timeline_df["Public Preview"].combine_first(timeline_df["Early Access"])
    timeline_df["Finish"] = timeline_df["GA"]
    timeline_df = timeline_df.dropna(subset=["Start"])

    if group_by != "Feature":
        timeline_df = (
            timeline_df
            .groupby(group_by)
            .agg(
                Start=("Start", "min"),
                Finish=("Finish", "max"),
                Status=("Status", lambda s: s.mode().iat[0] if not s.mode().empty else "Planned")
            )
            .reset_index()
        )

    if timeline_df.empty:
        st.info("No timeline data available.")
    else:
        fig = px.timeline(
            timeline_df,
            x_start="Start",
            x_end="Finish",
            y=group_by,
            color="Status",
            height=max(600, len(timeline_df) * 30),
            color_discrete_map={
                "Generally Available": "#2ca02c",
                "Public Preview": "#1f77b4",
                "Early Access": "#9467bd",
                "Planned": "#ff7f0e"
            }
        )
        fig.update_yaxes(autorange="reversed")
        fig.update_layout(
            title=f"Release Timeline by {group_by}",
            hovermode="y unified"
        )
        st.plotly_chart(fig, use_container_width=True)

# ── SUMMARY (UNCHANGED) ──────────────────────────
with tab_summary:
    st.subheader("Feature Status by Release Wave")

    wave_df = filtered.copy()
    wave_df["Release Wave"] = (
        wave_df["GA Wave"].where(wave_df["GA Wave"].str.strip() != "", wave_df["Preview Wave"])
        .fillna("No Wave")
    )

    summary = (
        wave_df.groupby(["Release Wave", "Status"])
        .size()
        .reset_index(name="Count")
    )

    fig = px.bar(
        summary,
        x="Release Wave",
        y="Count",
        color="Status",
        barmode="stack",
        height=500,
        title="Feature Lifecycle Status by Release Wave"
    )

    st.plotly_chart(fig, use_container_width=True)