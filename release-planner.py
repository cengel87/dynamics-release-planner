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
            # Extract individual objects for robust parsing
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
                except Exception as e:
                    # Silent skip for individual parsing errors
                    pass

        if len(features) < 100:  # Adjusted threshold
            st.error(f"Only {len(features)} valid features parsed — site format may have changed.")
            return None

        def clean(val):
            if not val:
                return ""
            return BeautifulSoup(str(val), "html.parser").get_text(" ", strip=True)

        def parse_date(val):
            if not val or val in ("", "N/A", "TBD"):
                return pd.NaT
            try:
                return pd.to_datetime(val, errors="coerce")
            except:
                return pd.NaT

        today = pd.Timestamp.now().normalize()
        rows = []

        for f in features:
            preview = parse_date(f.get("Public preview date"))
            ga = parse_date(f.get("GA date"))
            early = parse_date(f.get("Early access date"))
            last_updated = parse_date(f.get("Last Gitcommit date"))

            # Enhanced status logic
            status = "Planned"
            if pd.notna(ga) and ga <= today:
                status = "Generally Available"
            elif pd.notna(preview) and preview <= today:
                status = "Public Preview"
            elif pd.notna(early) and early <= today:
                status = "Early Access"

            # Calculate days to/from launch
            days_to_ga = None
            days_in_preview = None
            
            if pd.notna(ga):
                days_to_ga = (ga - today).days
            
            if pd.notna(preview) and pd.notna(ga):
                days_in_preview = (ga - preview).days

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
                "Preview Wave": str(f.get("Public Preview Release Wave", "")).strip(),
                "GA Wave": str(f.get("GA Release Wave", "")).strip(),
                "Status": status,
                "Release Plan ID": str(f.get("Release Plan ID", "")),
                "Last Updated": last_updated,
                "Days to GA": days_to_ga,
                "Days in Preview": days_in_preview,
            })

        df = pd.DataFrame(rows)
        
        # Clean up wave data
        df["Preview Wave"] = df["Preview Wave"].replace({"": "TBD", "None": "TBD"})
        df["GA Wave"] = df["GA Wave"].replace({"": "TBD", "None": "TBD"})
        
        # Create combined release wave
        df["Release Wave"] = df["GA Wave"].where(
            (df["GA Wave"] != "TBD") & (df["GA Wave"] != ""), 
            df["Preview Wave"]
        )
        
        df = df.sort_values("Last Updated", ascending=False, na_position="last")
        df["App"] = df["Product"].str.replace(" ", "+", regex=False)
        df["Link"] = "https://experience.dynamics.com/releaseplans?app=" + df["App"] + "&planID=" + df["Release Plan ID"] + "&rp=all-plans"
        
        return df

    except Exception as e:
        st.error(f"Error loading data: {e}")
        import traceback
        st.code(traceback.format_exc())
        return None

# ────────────────────────────────────────────────
# ANALYTICS FUNCTIONS
# ────────────────────────────────────────────────

def calculate_wave_metrics(df):
    """Calculate key metrics for each release wave"""
    metrics = []
    
    for wave in df["Release Wave"].unique():
        if wave == "TBD" or not wave:
            continue
            
        wave_data = df[df["Release Wave"] == wave]
        
        total_features = len(wave_data)
        ga_count = len(wave_data[wave_data["Status"] == "Generally Available"])
        preview_count = len(wave_data[wave_data["Status"] == "Public Preview"])
        planned_count = len(wave_data[wave_data["Status"] == "Planned"])
        
        completion_rate = (ga_count / total_features * 100) if total_features > 0 else 0
        
        # Calculate average time in preview for completed features
        completed = wave_data[
            (wave_data["Status"] == "Generally Available") & 
            (wave_data["Days in Preview"].notna())
        ]
        avg_preview_days = completed["Days in Preview"].mean() if len(completed) > 0 else None
        
        metrics.append({
            "Wave": wave,
            "Total Features": total_features,
            "GA": ga_count,
            "Preview": preview_count,
            "Planned": planned_count,
            "Completion %": completion_rate,
            "Avg Preview Days": avg_preview_days,
        })
    
    return pd.DataFrame(metrics).sort_values("Wave")

def get_upcoming_releases(df, days=90):
    """Get features releasing in the next N days"""
    today = pd.Timestamp.now().normalize()
    future_date = today + timedelta(days=days)
    
    upcoming = df[
        (df["GA"].notna()) & 
        (df["GA"] > today) & 
        (df["GA"] <= future_date)
    ].copy()
    
    return upcoming.sort_values("GA")

def analyze_product_velocity(df):
    """Analyze release velocity by product"""
    velocity = []
    
    for product in df["Product"].unique():
        if not product:
            continue
            
        prod_data = df[df["Product"] == product]
        
        total = len(prod_data)
        ga = len(prod_data[prod_data["Status"] == "Generally Available"])
        preview = len(prod_data[prod_data["Status"] == "Public Preview"])
        
        # Calculate recent update rate (last 30 days)
        today = pd.Timestamp.now()
        recent = prod_data[
            (prod_data["Last Updated"].notna()) & 
            ((today - prod_data["Last Updated"]).dt.days <= 30)
        ]
        
        velocity.append({
            "Product": product,
            "Total Features": total,
            "GA": ga,
            "Preview": preview,
            "Completion %": (ga / total * 100) if total > 0 else 0,
            "Recent Updates (30d)": len(recent),
        })
    
    return pd.DataFrame(velocity).sort_values("Total Features", ascending=False)

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

# Refresh button in top corner
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

    sel_product = st.multiselect(
        "Product",
        options=sorted(df["Product"].dropna().unique()),
        default=[]
    )

    sel_status = st.multiselect(
        "Status",
        options=sorted(df["Status"].unique()),
        default=[]
    )

    sel_wave = st.multiselect(
        "Release Wave",
        options=sorted([w for w in df["Release Wave"].unique() if w != "TBD"]),
        default=[]
    )

    sel_area = st.multiselect(
        "Investment Area",
        options=sorted(df["Area"].dropna().unique()),
        default=[]
    )

    # Date range filter
    st.subheader("Date Range")
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

    search = st.text_input("🔎 Keyword Search", placeholder="Search features, business value, details...")

# Apply filters
filtered = df.copy()

if sel_product:
    filtered = filtered[filtered["Product"].isin(sel_product)]

if sel_status:
    filtered = filtered[filtered["Status"].isin(sel_status)]

if sel_wave:
    filtered = filtered[filtered["Release Wave"].isin(sel_wave)]

if sel_area:
    filtered = filtered[filtered["Area"].isin(sel_area)]

if use_date_filter:
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    filtered = filtered[
        (filtered["GA"].notna()) & 
        (filtered["GA"] >= start) & 
        (filtered["GA"] <= end)
    ]

if search:
    s = search.lower()
    mask = (
        filtered["Feature"].str.lower().str.contains(s, na=False) |
        filtered["Business Value"].str.lower().str.contains(s, na=False) |
        filtered["Details"].str.lower().str.contains(s, na=False) |
        filtered["Area"].str.lower().str.contains(s, na=False) |
        filtered["Product"].str.lower().str.contains(s, na=False)
    )
    filtered = filtered[mask]

# ── Key Metrics ──────────────────────────────────
st.markdown(f"### 📊 Overview: {len(filtered):,} of {len(df):,} features")

metric_cols = st.columns(5)

status_counts = filtered["Status"].value_counts()
statuses = ["Planned", "Early Access", "Public Preview", "Generally Available"]
colors = ["🔵", "🟣", "🟡", "🟢"]

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
metric_cols[4].metric("🎯 Next 30 Days", upcoming_30)

st.divider()

# ── Main Tabs ────────────────────────────────────
tab_overview, tab_waves, tab_products, tab_timeline, tab_table, tab_recent = st.tabs([
    "📈 Executive Overview",
    "🌊 Release Wave Analysis", 
    "📦 Product Breakdown",
    "📅 Timeline View",
    "📋 Features Table",
    "🆕 Recent Updates"
])

# ── EXECUTIVE OVERVIEW ───────────────────────────
with tab_overview:
    st.subheader("Release Momentum & Trends")
    
    overview_cols = st.columns([2, 1])
    
    with overview_cols[0]:
        # Status distribution over time
        status_time = filtered[filtered["GA"].notna()].copy()
        status_time["Month"] = status_time["GA"].dt.to_period("M").astype(str)
        
        monthly_status = status_time.groupby(["Month", "Status"]).size().reset_index(name="Count")
        
        if not monthly_status.empty:
            fig_trend = px.line(
                monthly_status,
                x="Month",
                y="Count",
                color="Status",
                markers=True,
                title="Feature Releases by Month & Status",
                height=400,
                color_discrete_map={
                    "Generally Available": "#2ca02c",
                    "Public Preview": "#1f77b4",
                    "Early Access": "#9467bd",
                    "Planned": "#ff7f0e"
                }
            )
            fig_trend.update_layout(hovermode="x unified")
            st.plotly_chart(fig_trend, use_container_width=True)
        else:
            st.info("No dated releases to display trend")
    
    with overview_cols[1]:
        # Overall status pie
        status_dist = filtered["Status"].value_counts().reset_index()
        status_dist.columns = ["Status", "Count"]
        
        fig_pie = px.pie(
            status_dist,
            values="Count",
            names="Status",
            title="Current Status Distribution",
            height=400,
            color="Status",
            color_discrete_map={
                "Generally Available": "#2ca02c",
                "Public Preview": "#1f77b4",
                "Early Access": "#9467bd",
                "Planned": "#ff7f0e"
            }
        )
        st.plotly_chart(fig_pie, use_container_width=True)
    
    st.subheader("Upcoming Releases (Next 90 Days)")
    
    upcoming = get_upcoming_releases(filtered, days=90)
    
    if not upcoming.empty:
        # Group by month
        upcoming["Month"] = upcoming["GA"].dt.strftime("%Y-%m (%B)")
        monthly_upcoming = upcoming.groupby(["Month", "Product"]).size().reset_index(name="Count")
        
        fig_upcoming = px.bar(
            monthly_upcoming,
            x="Month",
            y="Count",
            color="Product",
            title="Planned GA Releases by Month & Product",
            height=400,
            text="Count"
        )
        fig_upcoming.update_traces(textposition="outside")
        st.plotly_chart(fig_upcoming, use_container_width=True)
        
        # Detailed list
        with st.expander(f"📋 View All {len(upcoming)} Upcoming Releases"):
            st.dataframe(
                upcoming[["Product", "Feature", "GA", "Days to GA", "Status", "Release Wave"]],
                use_container_width=True,
                hide_index=True
            )
    else:
        st.info("No releases scheduled in the next 90 days")

# ── RELEASE WAVE ANALYSIS ────────────────────────
with tab_waves:
    st.subheader("Release Wave Performance Metrics")
    
    wave_metrics = calculate_wave_metrics(filtered)
    
    if not wave_metrics.empty:
        # Wave comparison chart
        fig_wave = make_subplots(
            rows=1, cols=2,
            subplot_titles=("Features by Wave & Status", "Wave Completion Rates"),
            specs=[[{"type": "bar"}, {"type": "bar"}]]
        )
        
        # Stacked bar for status by wave
        for status in ["Planned", "Preview", "GA"]:
            if status in wave_metrics.columns:
                fig_wave.add_trace(
                    go.Bar(
                        name=status,
                        x=wave_metrics["Wave"],
                        y=wave_metrics[status],
                        text=wave_metrics[status],
                        textposition="inside"
                    ),
                    row=1, col=1
                )
        
        # Completion rate bars
        fig_wave.add_trace(
            go.Bar(
                name="Completion %",
                x=wave_metrics["Wave"],
                y=wave_metrics["Completion %"],
                text=wave_metrics["Completion %"].round(1).astype(str) + "%",
                textposition="outside",
                marker_color="#2ca02c"
            ),
            row=1, col=2
        )
        
        fig_wave.update_layout(
            barmode="stack",
            height=500,
            showlegend=True,
            hovermode="x unified"
        )
        fig_wave.update_yaxes(title_text="Feature Count", row=1, col=1)
        fig_wave.update_yaxes(title_text="Completion %", row=1, col=2)
        
        st.plotly_chart(fig_wave, use_container_width=True)
        
        # Detailed metrics table
        st.subheader("Detailed Wave Metrics")
        
        display_metrics = wave_metrics.copy()
        display_metrics["Completion %"] = display_metrics["Completion %"].round(1).astype(str) + "%"
        display_metrics["Avg Preview Days"] = display_metrics["Avg Preview Days"].round(0).fillna("N/A")
        
        st.dataframe(
            display_metrics,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Wave": st.column_config.TextColumn("Release Wave", width="medium"),
                "Total Features": st.column_config.NumberColumn("Total", format="%d"),
                "GA": st.column_config.NumberColumn("GA", format="%d"),
                "Preview": st.column_config.NumberColumn("Preview", format="%d"),
                "Planned": st.column_config.NumberColumn("Planned", format="%d"),
                "Completion %": st.column_config.TextColumn("Completion"),
                "Avg Preview Days": st.column_config.TextColumn("Avg Preview Duration"),
            }
        )
        
        # Wave deep dive
        st.subheader("Wave Deep Dive")
        selected_wave = st.selectbox(
            "Select a wave to analyze",
            options=sorted([w for w in filtered["Release Wave"].unique() if w != "TBD"])
        )
        
        if selected_wave:
            wave_data = filtered[filtered["Release Wave"] == selected_wave]
            
            wave_cols = st.columns(3)
            wave_cols[0].metric("Total Features", len(wave_data))
            wave_cols[1].metric(
                "GA Features", 
                len(wave_data[wave_data["Status"] == "Generally Available"])
            )
            wave_cols[2].metric(
                "In Progress",
                len(wave_data[wave_data["Status"].isin(["Public Preview", "Early Access"])])
            )
            
            # Product breakdown for this wave
            wave_product = wave_data.groupby(["Product", "Status"]).size().reset_index(name="Count")
            
            fig_wave_product = px.bar(
                wave_product,
                x="Product",
                y="Count",
                color="Status",
                title=f"{selected_wave} - Features by Product",
                height=400,
                color_discrete_map={
                    "Generally Available": "#2ca02c",
                    "Public Preview": "#1f77b4",
                    "Early Access": "#9467bd",
                    "Planned": "#ff7f0e"
                }
            )
            st.plotly_chart(fig_wave_product, use_container_width=True)
    else:
        st.info("No wave data available for analysis")

# ── PRODUCT BREAKDOWN ────────────────────────────
with tab_products:
    st.subheader("Product Release Velocity & Performance")
    
    velocity = analyze_product_velocity(filtered)
    
    if not velocity.empty:
        # Velocity visualization
        fig_velocity = px.scatter(
            velocity,
            x="Total Features",
            y="Completion %",
            size="Recent Updates (30d)",
            color="Product",
            hover_data=["GA", "Preview"],
            title="Product Velocity Matrix (Size = Recent Activity)",
            height=500,
            labels={
                "Total Features": "Total Features in Pipeline",
                "Completion %": "Completion Rate (%)"
            }
        )
        fig_velocity.add_hline(
            y=velocity["Completion %"].median(),
            line_dash="dash",
            annotation_text="Median Completion",
            line_color="gray"
        )
        st.plotly_chart(fig_velocity, use_container_width=True)
        
        # Product table
        st.subheader("Product Summary")
        
        display_velocity = velocity.copy()
        display_velocity["Completion %"] = display_velocity["Completion %"].round(1).astype(str) + "%"
        
        st.dataframe(
            display_velocity,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Product": st.column_config.TextColumn("Product", width="medium"),
                "Total Features": st.column_config.NumberColumn("Total", format="%d"),
                "GA": st.column_config.NumberColumn("GA", format="%d"),
                "Preview": st.column_config.NumberColumn("Preview", format="%d"),
                "Completion %": st.column_config.TextColumn("Completion"),
                "Recent Updates (30d)": st.column_config.NumberColumn("Recent Updates", format="%d"),
            }
        )
        
        # Product comparison
        st.subheader("Product Comparison")
        compare_products = st.multiselect(
            "Select products to compare",
            options=sorted(filtered["Product"].unique()),
            default=sorted(filtered["Product"].unique())[:3] if len(filtered["Product"].unique()) >= 3 else sorted(filtered["Product"].unique())
        )
        
        if compare_products:
            compare_data = filtered[filtered["Product"].isin(compare_products)]
            compare_status = compare_data.groupby(["Product", "Status"]).size().reset_index(name="Count")
            
            fig_compare = px.bar(
                compare_status,
                x="Product",
                y="Count",
                color="Status",
                barmode="group",
                title="Product Status Comparison",
                height=400,
                color_discrete_map={
                    "Generally Available": "#2ca02c",
                    "Public Preview": "#1f77b4",
                    "Early Access": "#9467bd",
                    "Planned": "#ff7f0e"
                }
            )
            st.plotly_chart(fig_compare, use_container_width=True)
    else:
        st.info("No product data available")

# ── TIMELINE VIEW ────────────────────────────────
with tab_timeline:
    st.subheader("Release Timeline Visualization")

    group_by = st.selectbox(
        "Group timeline by",
        ["Feature", "Product", "Area"],
        index=1
    )

    timeline_df = filtered.copy()
    timeline_df["Start"] = timeline_df["Public Preview"].combine_first(
        timeline_df["Early Access"]
    ).combine_first(timeline_df["GA"])
    timeline_df["Finish"] = timeline_df["GA"].combine_first(timeline_df["Public Preview"])
    timeline_df = timeline_df.dropna(subset=["Start"])

    # Limit to reasonable number for readability
    max_items = st.slider("Maximum items to display", 10, 100, 50)
    
    if group_by != "Feature":
        timeline_df = (
            timeline_df
            .groupby(group_by)
            .agg(
                Start=("Start", "min"),
                Finish=("Finish", "max"),
                Status=("Status", lambda s: s.mode().iat[0] if not s.mode().empty else "Planned"),
                Count=("Feature", "count")
            )
            .reset_index()
            .sort_values("Count", ascending=False)
            .head(max_items)
        )
    else:
        timeline_df = timeline_df.sort_values("GA", ascending=False).head(max_items)

    if timeline_df.empty:
        st.info("No timeline data available with current filters")
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
            },
            title=f"Release Timeline by {group_by} (Top {len(timeline_df)} items)"
        )
        fig.update_yaxes(autorange="reversed")
        fig.update_layout(hovermode="y unified")
        st.plotly_chart(fig, use_container_width=True)

# ── FEATURES TABLE ───────────────────────────────
with tab_table:
    st.subheader("Detailed Features List")
    
    display_cols = [
        "Product", "Feature", "Status", "Public Preview", "GA",
        "Release Wave", "Area", "Enabled For", "Days to GA", "Last Updated", "Link"
    ]

    event = st.dataframe(
        filtered[display_cols],
        column_config={
            "Link": st.column_config.LinkColumn(
                "Details",
                display_text="View →",
                help="Link to release plan details",
                validate="^https://",
            ),
            "Days to GA": st.column_config.NumberColumn(
                "Days to GA",
                format="%d",
                help="Days until GA (negative = already released)"
            ),
            "Last Updated": st.column_config.DateColumn(
                "Last Updated",
                format="YYYY-MM-DD"
            ),
            "Public Preview": st.column_config.DateColumn(
                "Preview Date",
                format="YYYY-MM-DD"
            ),
            "GA": st.column_config.DateColumn(
                "GA Date",
                format="YYYY-MM-DD"
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
    
    with download_cols[1]:
        st.download_button(
            "📥 Download Excel",
            filtered.to_csv(index=False).encode('utf-8'),
            file_name=f"d365_releases_{datetime.now():%Y%m%d}.csv",
            mime="text/csv",
            use_container_width=True
        )

    # Feature details on selection
    selected = event.selection.get("rows", [])
    if selected:
        row = filtered.iloc[selected[0]]
        st.divider()
        st.subheader(f"📌 {row['Feature']}")
        
        detail_cols = st.columns(4)
        detail_cols[0].metric("Product", row["Product"])
        detail_cols[1].metric("Status", row["Status"])
        detail_cols[2].metric("Release Wave", row["Release Wave"])
        detail_cols[3].metric("Area", row["Area"])
        
        if row["Business Value"]:
            st.markdown("**💼 Business Value:**")
            st.info(row["Business Value"])
        
        if row["Details"]:
            st.markdown("**📝 Details:**")
            st.info(row["Details"])
        
        if row["Enabled For"]:
            st.markdown(f"**👥 Enabled For:** {row['Enabled For']}")
        
        date_cols = st.columns(3)
        if pd.notna(row["Public Preview"]):
            date_cols[0].metric("Preview Date", row["Public Preview"].strftime("%Y-%m-%d"))
        if pd.notna(row["GA"]):
            date_cols[1].metric("GA Date", row["GA"].strftime("%Y-%m-%d"))
        if pd.notna(row["Days to GA"]):
            days = int(row["Days to GA"])
            if days > 0:
                date_cols[2].metric("Days Until GA", days)
            elif days < 0:
                date_cols[2].metric("Days Since GA", abs(days))
        
        st.link_button("🔗 View on Microsoft Release Planner", row["Link"], use_container_width=True)

# ── RECENT UPDATES ───────────────────────────────
with tab_recent:
    st.subheader("Recently Updated Features")
    
    update_period = st.selectbox(
        "Time period",
        [("Last 7 Days", 7), ("Last 14 Days", 14), ("Last 30 Days", 30), ("Last 60 Days", 60)],
        format_func=lambda x: x[0]
    )
    
    days = update_period[1]
    today = pd.Timestamp.now()
    recent = filtered[
        (filtered["Last Updated"].notna()) & 
        ((today - filtered["Last Updated"]).dt.days <= days)
    ].copy()

    if recent.empty:
        st.info(f"No features updated in the last {days} days")
    else:
        st.markdown(f"**{len(recent)} features updated in the last {days} days**")
        
        # Update activity by product
        recent_by_product = recent.groupby("Product").size().reset_index(name="Updates")
        recent_by_product = recent_by_product.sort_values("Updates", ascending=False)
        
        fig_recent = px.bar(
            recent_by_product,
            x="Product",
            y="Updates",
            title=f"Update Activity by Product (Last {days} Days)",
            height=400,
            color="Updates",
            color_continuous_scale="Blues"
        )
        fig_recent.update_traces(texttemplate='%{y}', textposition='outside')
        st.plotly_chart(fig_recent, use_container_width=True)
        
        # Recent updates table
        st.dataframe(
            recent[display_cols],
            column_config={
                "Link": st.column_config.LinkColumn(
                    "Details",
                    display_text="View →",
                    help="Link to release plan details",
                    validate="^https://",
                ),
                "Last Updated": st.column_config.DateColumn(
                    "Last Updated",
                    format="YYYY-MM-DD"
                ),
            },
            use_container_width=True,
            hide_index=True
        )

# ── Footer ───────────────────────────────────────
st.divider()
st.caption("Data source: Microsoft Dynamics 365 & Power Platform Release Plans | Built with Streamlit")