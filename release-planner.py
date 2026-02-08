"""
D365 & Power Platform Release Tracker — Team Edition
=====================================================
Enhanced collaborative release tracking with:
- Supabase persistence (watchlists, notes, saved views)
- Change detection & history
- Team authentication
- Enablement analysis

Deploy: Streamlit Community Cloud + Supabase (free tier)
"""

import json
import re
import hashlib
import hmac
import time
import requests
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from urllib.parse import quote_plus
import urllib.parse

try:
    from supabase import create_client, Client
    HAS_SUPABASE = True
except ImportError:
    HAS_SUPABASE = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

# ────────────────────────────────────────────────
# PAGE CONFIG
# ────────────────────────────────────────────────
st.set_page_config(
    page_title="D365 Release Tracker",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ────────────────────────────────────────────────
# CONSTANTS
# ────────────────────────────────────────────────
API_URL = "https://releaseplans.microsoft.com/en-US/allreleaseplans/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 "
        "D365ReleaseTracker/2.0"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

STATUS_COLORS = {
    "Generally Available": "#28a745",
    "Public Preview": "#17a2b8",
    "Early Access": "#9467bd",
    "Planned": "#6c757d",
}

STATUS_EMOJI = {
    "Generally Available": "🟢",
    "Public Preview": "🔵",
    "Early Access": "🟣",
    "Planned": "⚪",
}

CHANGE_TYPE_LABELS = {
    "new_feature": "🆕 New Feature",
    "date_change": "📅 Date Changed",
    "status_change": "🔄 Status Changed",
    "description_change": "📝 Description Updated",
    "wave_change": "🌊 Wave Changed",
    "removed": "🗑️ Removed",
}

TRACKED_FIELDS = [
    "GA date", "Public preview date", "Early access date",
    "GA Release Wave", "Public Preview Release Wave",
    "Enabled for", "Business value", "Feature details",
    "Investment area",
]


# ────────────────────────────────────────────────
# DATABASE LAYER (Supabase)
# ────────────────────────────────────────────────

def get_supabase() -> "Client | None":
    """Get or create Supabase client from Streamlit secrets."""
    if not HAS_SUPABASE:
        return None
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        if "supabase_client" not in st.session_state:
            st.session_state.supabase_client = create_client(url, key)
        return st.session_state.supabase_client
    except Exception:
        return None


def db_available() -> bool:
    return get_supabase() is not None


# ── Auth helpers ──────────────────────────────────

def hash_password(password: str) -> str:
    """Simple SHA-256 hash for passwords. Good enough for internal tool."""
    return hashlib.sha256(password.encode()).hexdigest()


def authenticate_user(username: str, password: str) -> dict | None:
    """Check credentials against DB. Returns user dict or None."""
    sb = get_supabase()
    if not sb:
        return None
    try:
        pwd_hash = hash_password(password)
        result = sb.table("users").select("*").eq(
            "username", username
        ).eq("password_hash", pwd_hash).execute()
        if result.data:
            user = result.data[0]
            # Update last login
            sb.table("users").update(
                {"last_login": datetime.utcnow().isoformat()}
            ).eq("id", user["id"]).execute()
            return user
        return None
    except Exception:
        return None


def register_user(username: str, display_name: str, password: str) -> bool:
    """Register a new team member."""
    sb = get_supabase()
    if not sb:
        return False
    try:
        sb.table("users").insert({
            "username": username,
            "display_name": display_name,
            "password_hash": hash_password(password),
            "role": "member",
        }).execute()
        return True
    except Exception:
        return False


# ── Watchlist helpers ─────────────────────────────

def get_user_watchlist(user_id: str) -> list[str]:
    """Get list of release_plan_ids on user's watchlist."""
    sb = get_supabase()
    if not sb:
        return []
    try:
        result = sb.table("watchlist").select("release_plan_id").eq(
            "user_id", user_id
        ).execute()
        return [r["release_plan_id"] for r in result.data]
    except Exception:
        return []


def get_watchlist_details(user_id: str) -> list[dict]:
    """Get full watchlist with feature details."""
    sb = get_supabase()
    if not sb:
        return []
    try:
        result = sb.table("watchlist").select("*").eq(
            "user_id", user_id
        ).order("added_at", desc=True).execute()
        return result.data or []
    except Exception:
        return []


def add_to_watchlist(user_id: str, release_plan_id: str,
                     feature_name: str, product_name: str) -> bool:
    sb = get_supabase()
    if not sb:
        return False
    try:
        sb.table("watchlist").upsert({
            "user_id": user_id,
            "release_plan_id": release_plan_id,
            "feature_name": feature_name,
            "product_name": product_name,
        }, on_conflict="user_id,release_plan_id").execute()
        return True
    except Exception:
        return False


def remove_from_watchlist(user_id: str, release_plan_id: str) -> bool:
    sb = get_supabase()
    if not sb:
        return False
    try:
        sb.table("watchlist").delete().eq(
            "user_id", user_id
        ).eq("release_plan_id", release_plan_id).execute()
        return True
    except Exception:
        return False


# ── Notes helpers ─────────────────────────────────

def get_notes(release_plan_id: str) -> list[dict]:
    """Get all notes for a feature, with user info."""
    sb = get_supabase()
    if not sb:
        return []
    try:
        result = sb.table("notes").select(
            "*, users(display_name, username)"
        ).eq("release_plan_id", release_plan_id).order(
            "created_at", desc=True
        ).execute()
        return result.data or []
    except Exception:
        return []


def add_note(user_id: str, release_plan_id: str, content: str) -> bool:
    sb = get_supabase()
    if not sb:
        return False
    try:
        sb.table("notes").insert({
            "user_id": user_id,
            "release_plan_id": release_plan_id,
            "content": content,
        }).execute()
        return True
    except Exception:
        return False


def update_note(note_id: str, content: str) -> bool:
    sb = get_supabase()
    if not sb:
        return False
    try:
        sb.table("notes").update({
            "content": content,
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", note_id).execute()
        return True
    except Exception:
        return False


def delete_note(note_id: str) -> bool:
    sb = get_supabase()
    if not sb:
        return False
    try:
        sb.table("notes").delete().eq("id", note_id).execute()
        return True
    except Exception:
        return False


# ── Saved Views helpers ───────────────────────────

def get_saved_views(user_id: str) -> list[dict]:
    sb = get_supabase()
    if not sb:
        return []
    try:
        result = sb.table("saved_views").select("*").or_(
            f"user_id.eq.{user_id},is_shared.eq.true"
        ).order("name").execute()
        return result.data or []
    except Exception:
        return []


def save_view(user_id: str, name: str, description: str,
              config: dict, is_shared: bool = False) -> bool:
    sb = get_supabase()
    if not sb:
        return False
    try:
        sb.table("saved_views").insert({
            "user_id": user_id,
            "name": name,
            "description": description,
            "config": config,
            "is_shared": is_shared,
        }).execute()
        return True
    except Exception:
        return False


def delete_saved_view(view_id: str) -> bool:
    sb = get_supabase()
    if not sb:
        return False
    try:
        sb.table("saved_views").delete().eq("id", view_id).execute()
        return True
    except Exception:
        return False


# ── Change Detection helpers ──────────────────────

def get_latest_snapshot(release_plan_id: str) -> dict | None:
    sb = get_supabase()
    if not sb:
        return None
    try:
        result = sb.table("feature_snapshots").select("*").eq(
            "release_plan_id", release_plan_id
        ).order("fetched_at", desc=True).limit(1).execute()
        return result.data[0] if result.data else None
    except Exception:
        return None


def save_snapshot(release_plan_id: str, snapshot_data: dict) -> bool:
    sb = get_supabase()
    if not sb:
        return False
    try:
        sb.table("feature_snapshots").insert({
            "release_plan_id": release_plan_id,
            "snapshot_data": snapshot_data,
        }).execute()
        return True
    except Exception:
        return False


def log_change(release_plan_id: str, feature_name: str,
               product_name: str, change_type: str,
               field_changed: str = None,
               old_value: str = None, new_value: str = None) -> bool:
    sb = get_supabase()
    if not sb:
        return False
    try:
        sb.table("change_log").insert({
            "release_plan_id": release_plan_id,
            "feature_name": feature_name,
            "product_name": product_name,
            "change_type": change_type,
            "field_changed": field_changed,
            "old_value": old_value,
            "new_value": new_value,
        }).execute()
        return True
    except Exception:
        return False


def get_recent_changes(days: int = 30, limit: int = 200) -> list[dict]:
    sb = get_supabase()
    if not sb:
        return []
    try:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        result = sb.table("change_log").select("*").gte(
            "detected_at", cutoff
        ).order("detected_at", desc=True).limit(limit).execute()
        return result.data or []
    except Exception:
        return []


def get_feature_changes(release_plan_id: str) -> list[dict]:
    sb = get_supabase()
    if not sb:
        return []
    try:
        result = sb.table("change_log").select("*").eq(
            "release_plan_id", release_plan_id
        ).order("detected_at", desc=True).execute()
        return result.data or []
    except Exception:
        return []


def get_changed_feature_ids(days: int = 30) -> set:
    """Get set of release_plan_ids that have changes in the last N days."""
    sb = get_supabase()
    if not sb:
        return set()
    try:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        result = sb.table("change_log").select("release_plan_id").gte(
            "detected_at", cutoff
        ).execute()
        return {r["release_plan_id"] for r in (result.data or [])}
    except Exception:
        return set()


# ── Refresh helpers ───────────────────────────────

def start_refresh_log() -> str | None:
    sb = get_supabase()
    if not sb:
        return None
    try:
        result = sb.table("refresh_log").insert({
            "status": "running",
        }).execute()
        return result.data[0]["id"] if result.data else None
    except Exception:
        return None


def complete_refresh_log(log_id: str, total: int, new: int,
                         changed: int, status: str = "completed",
                         error: str = None):
    sb = get_supabase()
    if not sb:
        return
    try:
        sb.table("refresh_log").update({
            "completed_at": datetime.utcnow().isoformat(),
            "total_features": total,
            "new_features": new,
            "changed_features": changed,
            "status": status,
            "error_message": error,
        }).eq("id", log_id).execute()
    except Exception:
        pass


def detect_changes(features: list[dict]) -> tuple[int, int]:
    """
    Compare fresh features against stored snapshots.
    Returns (new_count, changed_count).
    """
    sb = get_supabase()
    if not sb:
        return 0, 0

    new_count = 0
    changed_count = 0

    for f in features:
        rpid = f.get("Release Plan ID", "")
        if not rpid:
            continue

        prev = get_latest_snapshot(rpid)

        if not prev:
            # New feature
            new_count += 1
            save_snapshot(rpid, f)
            log_change(rpid, f.get("Feature name", ""),
                      f.get("Product name", ""), "new_feature")
        else:
            # Compare tracked fields
            prev_data = prev.get("snapshot_data", {})
            changes_found = False

            for field in TRACKED_FIELDS:
                old_val = str(prev_data.get(field, "")).strip()
                new_val = str(f.get(field, "")).strip()

                if old_val != new_val:
                    changes_found = True
                    # Determine change type
                    if field in ("GA date", "Public preview date",
                                "Early access date"):
                        ctype = "date_change"
                    elif field in ("GA Release Wave",
                                  "Public Preview Release Wave"):
                        ctype = "wave_change"
                    elif field in ("Business value", "Feature details"):
                        ctype = "description_change"
                    else:
                        ctype = "status_change"

                    log_change(
                        rpid, f.get("Feature name", ""),
                        f.get("Product name", ""),
                        ctype, field, old_val[:500], new_val[:500]
                    )

            if changes_found:
                changed_count += 1
                save_snapshot(rpid, f)

    return new_count, changed_count


# ────────────────────────────────────────────────
# DATA FETCHING & PARSING
# ────────────────────────────────────────────────

def clean_html(val):
    """Remove HTML tags from text."""
    if not val:
        return ""
    if HAS_BS4:
        return BeautifulSoup(str(val), "html.parser").get_text(" ", strip=True)
    # Fallback: regex strip
    return re.sub(r'<[^>]+>', ' ', str(val)).strip()


def parse_date(val):
    """Parse date strings to pandas datetime."""
    if not val or val in ("", "N/A", "TBD"):
        return pd.NaT
    try:
        return pd.to_datetime(val, errors="coerce")
    except Exception:
        return pd.NaT


def parse_features_from_json(raw_data: dict) -> list[dict]:
    """Parse raw API JSON into list of feature dicts."""
    results = raw_data.get("results", [])
    if not results:
        return []
    return [f for f in results if isinstance(f, dict) and "Feature name" in f]


@st.cache_data(ttl=3600 * 4, show_spinner="Fetching latest release plans…")
def fetch_release_plans_api() -> list[dict] | None:
    """
    Fetch raw features from Microsoft's Release Plans API.
    Returns list of raw feature dicts, or None on failure.
    Handles pagination if morerecords is true.
    """
    try:
        all_features = []
        page = 1
        max_pages = 10  # Safety limit

        while page <= max_pages:
            url = API_URL if page == 1 else f"{API_URL}?page={page}"
            resp = requests.get(url, headers=HEADERS, timeout=90)
            resp.raise_for_status()

            raw_text = resp.text.strip()

            # Try direct JSON parse first
            try:
                data = json.loads(raw_text)
                features = parse_features_from_json(data)
                all_features.extend(features)

                if not data.get("morerecords", False):
                    break
                page += 1
                continue
            except json.JSONDecodeError:
                pass

            # Fallback: regex extraction for malformed JSON
            wrapper_match = re.search(
                r'\{[^}]*"totalrecords"\s*:\s*"[^"]+"[^}]*"results"\s*:\s*\[\s*(.+?)\s*\]\s*\}',
                raw_text, re.DOTALL | re.MULTILINE
            )
            if wrapper_match:
                array_str = re.sub(r',\s*$', '', wrapper_match.group(1).strip())
                obj_strings = re.findall(
                    r'\s*(\{.+?\})\s*(?:,|$)', array_str, re.DOTALL
                )
                for obj_str in obj_strings:
                    obj_str = obj_str.strip()
                    if obj_str.count('"') % 2 != 0:
                        obj_str += '"'
                    obj_str = re.sub(r',\s*}', '}', obj_str)
                    try:
                        f = json.loads(obj_str)
                        if isinstance(f, dict) and "Feature name" in f:
                            all_features.append(f)
                    except Exception:
                        pass
            break  # No pagination info available in fallback mode

        return all_features if len(all_features) > 50 else None

    except Exception as e:
        st.error(f"Error fetching data: {e}")
        return None


def load_local_json() -> list[dict] | None:
    """Load from local JSON file as fallback."""
    import os
    paths = [
        "releaseplans.json",
        os.path.join(os.path.dirname(__file__), "releaseplans.json"),
    ]
    for path in paths:
        if os.path.exists(path):
            try:
                with open(path) as f:
                    data = json.load(f)
                return parse_features_from_json(data)
            except Exception:
                continue
    return None


def build_dataframe(features: list[dict]) -> pd.DataFrame:
    """Transform raw feature dicts into a clean DataFrame."""
    today = pd.Timestamp.now().normalize()
    rows = []

    for f in features:
        early_access = parse_date(f.get("Early access date"))
        preview = parse_date(f.get("Public preview date"))
        ga = parse_date(f.get("GA date"))
        last_updated = parse_date(f.get("Last Gitcommit date"))

        # Derive status from dates
        status = "Planned"
        if pd.notna(ga) and ga <= today:
            status = "Generally Available"
        elif pd.notna(preview) and preview <= today:
            status = "Public Preview"
        elif pd.notna(early_access) and early_access <= today:
            status = "Early Access"

        days_to_ga = (ga - today).days if pd.notna(ga) else None

        # Build release planner link
        product = f.get("Product name", "")
        feature = f.get("Feature name", "")
        app_name = product.replace("Dynamics 365 ", "").replace("Microsoft ", "").strip()
        search_link = (
            f"https://releaseplans.microsoft.com/en-us/"
            f"?app={urllib.parse.quote(app_name)}&q={urllib.parse.quote(feature)}"
        )

        rows.append({
            "Product name": clean_html(f.get("Product name")),
            "Feature name": clean_html(f.get("Feature name")),
            "Release Plan ID": str(f.get("Release Plan ID", "")),
            "ProductId": str(f.get("ProductId", "")),
            "Early access date": early_access,
            "Public preview date": preview,
            "GA date": ga,
            "Public Preview Release Wave": str(f.get("Public Preview Release Wave", "")).strip(),
            "GA Release Wave": str(f.get("GA Release Wave", "")).strip(),
            "Investment area": clean_html(f.get("Investment area")),
            "Business value": clean_html(f.get("Business value")),
            "Feature details": clean_html(f.get("Feature details")),
            "Enabled for": clean_html(f.get("Enabled for")),
            "Last Gitcommit date": last_updated,
            "Status": status,
            "Days to GA": days_to_ga,
            "Search Link": search_link,
        })

    df = pd.DataFrame(rows)
    df = df.replace({"": None, "None": None})

    # Combined release wave
    df["Release Wave"] = df["GA Release Wave"].where(
        df["GA Release Wave"].notna() & (df["GA Release Wave"] != ""),
        df["Public Preview Release Wave"]
    )

    df = df.sort_values("Last Gitcommit date", ascending=False, na_position="last")
    return df


@st.cache_data(ttl=3600 * 4, show_spinner="Loading release data…")
def get_data() -> pd.DataFrame | None:
    """Main data loading function. Tries API first, then local file."""
    features = fetch_release_plans_api()
    if not features:
        features = load_local_json()
    if not features:
        return None
    return build_dataframe(features)


def refresh_with_change_detection():
    """Full refresh with change detection against stored snapshots."""
    features = fetch_release_plans_api()
    if not features:
        features = load_local_json()
    if not features:
        st.error("Could not fetch data")
        return

    log_id = start_refresh_log()

    try:
        new_count, changed_count = detect_changes(features)
        if log_id:
            complete_refresh_log(
                log_id, len(features), new_count, changed_count
            )
        st.success(
            f"Refresh complete: {len(features)} features, "
            f"{new_count} new, {changed_count} changed"
        )
    except Exception as e:
        if log_id:
            complete_refresh_log(log_id, 0, 0, 0, "failed", str(e))
        st.error(f"Refresh failed: {e}")


# ────────────────────────────────────────────────
# SESSION STATE INIT
# ────────────────────────────────────────────────

def init_session_state():
    defaults = {
        "authenticated": False,
        "user": None,
        "user_id": None,
        "show_login": True,
        "active_tab": "Overview",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_session_state()


# ────────────────────────────────────────────────
# AUTH UI
# ────────────────────────────────────────────────

def show_auth_ui():
    """Show login/register forms. Returns True if authenticated."""
    if not db_available():
        # No DB configured — run in demo mode
        st.session_state.authenticated = True
        st.session_state.user = {"display_name": "Demo User", "id": "demo", "role": "admin"}
        st.session_state.user_id = "demo"
        return True

    if st.session_state.authenticated:
        return True

    st.markdown("## 🔐 Team Login")
    st.caption("Internal tool — team members only")

    login_tab, register_tab = st.tabs(["Login", "Register"])

    with login_tab:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login", use_container_width=True)

            if submitted and username and password:
                user = authenticate_user(username, password)
                if user:
                    st.session_state.authenticated = True
                    st.session_state.user = user
                    st.session_state.user_id = user["id"]
                    st.rerun()
                else:
                    st.error("Invalid credentials")

    with register_tab:
        with st.form("register_form"):
            new_user = st.text_input("Username", key="reg_user")
            new_name = st.text_input("Display Name", key="reg_name")
            new_pass = st.text_input("Password", type="password", key="reg_pass")
            new_pass2 = st.text_input("Confirm Password", type="password", key="reg_pass2")
            reg_submitted = st.form_submit_button("Register", use_container_width=True)

            if reg_submitted:
                if not all([new_user, new_name, new_pass, new_pass2]):
                    st.error("All fields required")
                elif new_pass != new_pass2:
                    st.error("Passwords don't match")
                elif len(new_pass) < 6:
                    st.error("Password must be at least 6 characters")
                elif register_user(new_user, new_name, new_pass):
                    st.success("Registered! Please login.")
                else:
                    st.error("Username may already exist")

    return False


# ────────────────────────────────────────────────
# FILTER APPLICATION
# ────────────────────────────────────────────────

def apply_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    """Apply a dict of filters to the dataframe."""
    filtered = df.copy()

    if filters.get("products"):
        filtered = filtered[filtered["Product name"].isin(filters["products"])]
    if filters.get("statuses"):
        filtered = filtered[filtered["Status"].isin(filters["statuses"])]
    if filters.get("waves"):
        filtered = filtered[filtered["Release Wave"].isin(filters["waves"])]
    if filters.get("areas"):
        filtered = filtered[filtered["Investment area"].isin(filters["areas"])]
    if filters.get("enabled_for"):
        filtered = filtered[filtered["Enabled for"].isin(filters["enabled_for"])]
    if filters.get("search"):
        s = filters["search"].lower()
        mask = (
            filtered["Feature name"].str.lower().str.contains(s, na=False) |
            filtered["Business value"].str.lower().str.contains(s, na=False) |
            filtered["Feature details"].str.lower().str.contains(s, na=False) |
            filtered["Investment area"].str.lower().str.contains(s, na=False) |
            filtered["Product name"].str.lower().str.contains(s, na=False)
        )
        filtered = filtered[mask]
    if filters.get("date_start") and filters.get("date_end"):
        start = pd.Timestamp(filters["date_start"])
        end = pd.Timestamp(filters["date_end"])
        filtered = filtered[
            (filtered["GA date"].notna()) &
            (filtered["GA date"] >= start) &
            (filtered["GA date"] <= end)
        ]

    return filtered


# ────────────────────────────────────────────────
# UI COMPONENTS
# ────────────────────────────────────────────────

def render_feature_card(row: pd.Series, user_id: str = None,
                        watchlist_ids: set = None, show_watchlist: bool = True):
    """Render a feature as an expander card with details, notes, watchlist."""
    rpid = row.get("Release Plan ID", "")
    status = row.get("Status", "Planned")
    emoji = STATUS_EMOJI.get(status, "⚪")

    # Check if changed recently
    changed_ids = st.session_state.get("changed_feature_ids", set())
    changed_badge = " 🔔" if rpid in changed_ids else ""

    watched = rpid in (watchlist_ids or set())
    watch_icon = "⭐" if watched else ""

    title = f"{emoji} {watch_icon} {row['Feature name']}{changed_badge}"

    with st.expander(title, expanded=False):
        cols = st.columns([2, 1, 1, 1])
        cols[0].markdown(f"**Product:** {row['Product name']}")
        cols[1].markdown(f"**Status:** {status}")
        wave = row.get("Release Wave", "")
        cols[2].markdown(f"**Wave:** {wave if wave else 'TBD'}")
        enabled = row.get("Enabled for", "")
        cols[3].markdown(f"**Enabled:** {enabled if enabled else 'N/A'}")

        # Dates row
        date_cols = st.columns(4)
        if pd.notna(row.get("Early access date")):
            date_cols[0].metric("Early Access", row["Early access date"].strftime("%Y-%m-%d"))
        if pd.notna(row.get("Public preview date")):
            date_cols[1].metric("Preview", row["Public preview date"].strftime("%Y-%m-%d"))
        if pd.notna(row.get("GA date")):
            date_cols[2].metric("GA Date", row["GA date"].strftime("%Y-%m-%d"))
        if row.get("Days to GA") is not None and pd.notna(row["Days to GA"]):
            days = int(row["Days to GA"])
            if days > 0:
                date_cols[3].metric("Days Until GA", days)
            elif days == 0:
                date_cols[3].metric("GA", "Today! 🎉")
            else:
                date_cols[3].metric("Days Since GA", abs(days))

        # Business value
        bv = row.get("Business value")
        if bv and str(bv) != "None":
            st.markdown("**💼 Business Value:**")
            st.info(bv[:800] + ("…" if len(str(bv)) > 800 else ""))

        # Feature details
        fd = row.get("Feature details")
        if fd and str(fd) != "None":
            st.markdown("**📝 Feature Details:**")
            st.caption(fd[:600] + ("…" if len(str(fd)) > 600 else ""))

        # Action buttons
        btn_cols = st.columns([1, 1, 2])

        if show_watchlist and user_id and user_id != "demo":
            if watched:
                if btn_cols[0].button("⭐ Remove from Watchlist",
                                      key=f"unwatch_{rpid}",
                                      use_container_width=True):
                    remove_from_watchlist(user_id, rpid)
                    st.rerun()
            else:
                if btn_cols[0].button("☆ Add to Watchlist",
                                      key=f"watch_{rpid}",
                                      use_container_width=True):
                    add_to_watchlist(
                        user_id, rpid,
                        row["Feature name"], row["Product name"]
                    )
                    st.rerun()

        link = row.get("Search Link", "")
        if link:
            btn_cols[1].link_button("🔍 View on Microsoft", link,
                                    use_container_width=True)

        # Notes section
        if user_id and user_id != "demo" and db_available():
            st.markdown("---")
            st.markdown("**💬 Team Notes:**")

            notes = get_notes(rpid)
            for note in notes:
                user_info = note.get("users", {})
                author = user_info.get("display_name", "Unknown") if user_info else "Unknown"
                created = note.get("created_at", "")[:10]

                note_cols = st.columns([5, 1])
                note_cols[0].markdown(f"**{author}** ({created}): {note['content']}")

                # Allow editing/deleting own notes
                if note.get("user_id") == user_id:
                    if note_cols[1].button("🗑️", key=f"del_note_{note['id']}"):
                        delete_note(note["id"])
                        st.rerun()

            # Add note form
            new_note = st.text_input(
                "Add a note",
                key=f"note_input_{rpid}",
                placeholder="Type your note here…"
            )
            if st.button("Add Note", key=f"add_note_{rpid}"):
                if new_note:
                    add_note(user_id, rpid, new_note)
                    st.rerun()

        # Change history
        if db_available() and rpid in changed_ids:
            st.markdown("---")
            st.markdown("**🔔 Recent Changes:**")
            changes = get_feature_changes(rpid)
            for c in changes[:5]:
                ctype = CHANGE_TYPE_LABELS.get(c["change_type"], c["change_type"])
                detected = c.get("detected_at", "")[:10]
                field = c.get("field_changed", "")
                old_v = c.get("old_value", "")[:100]
                new_v = c.get("new_value", "")[:100]

                if field:
                    st.caption(
                        f"{ctype} — **{field}**: "
                        f"~~{old_v}~~ → {new_v} ({detected})"
                    )
                else:
                    st.caption(f"{ctype} ({detected})")


# ────────────────────────────────────────────────
# MAIN APP
# ────────────────────────────────────────────────

def main():
    # Header
    st.title("🚀 D365 & Power Platform Release Tracker")

    # Auth check
    if not show_auth_ui():
        return

    user = st.session_state.user
    user_id = st.session_state.user_id

    # User bar
    header_cols = st.columns([4, 1, 1])
    header_cols[0].caption(
        f"Welcome, **{user['display_name']}** | "
        f"Last Refreshed: {datetime.utcnow():%Y-%m-%d %H:%M UTC}"
    )
    if db_available():
        if header_cols[1].button("🔄 Refresh & Detect Changes", use_container_width=True):
            fetch_release_plans_api.clear()
            get_data.clear()
            with st.spinner("Refreshing data and detecting changes…"):
                refresh_with_change_detection()
            st.rerun()
    if header_cols[2].button("🚪 Logout", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.user = None
        st.session_state.user_id = None
        st.rerun()

    # Load data
    df = get_data()
    if df is None or df.empty:
        st.error("Could not load release plan data. Check API connectivity.")
        # Try local fallback
        if st.button("Load from local file"):
            features = load_local_json()
            if features:
                df = build_dataframe(features)
                st.success(f"Loaded {len(df)} features from local file")
            else:
                st.error("No local file found. Place releaseplans.json alongside the app.")
        st.stop()

    # Load changed feature IDs for badges
    if db_available():
        st.session_state["changed_feature_ids"] = get_changed_feature_ids(days=14)
    else:
        st.session_state["changed_feature_ids"] = set()

    # Load watchlist
    watchlist_ids = set()
    if user_id and user_id != "demo" and db_available():
        watchlist_ids = set(get_user_watchlist(user_id))

    # ── Sidebar Filters ──────────────────────────
    with st.sidebar:
        st.header("🔍 Filters")

        # Search
        search = st.text_input("🔎 Search", placeholder="Keywords…",
                               label_visibility="collapsed")

        st.divider()

        # Wave selector
        all_waves = sorted([w for w in df["Release Wave"].dropna().unique() if w])
        sel_wave = st.multiselect("Release Wave", options=all_waves, default=[])

        # Product filter
        all_products = sorted(df["Product name"].dropna().unique())
        sel_product = st.multiselect("Product", options=all_products, default=[])

        # Status filter
        sel_status = st.multiselect(
            "Status",
            options=["Generally Available", "Public Preview", "Early Access", "Planned"],
            default=[]
        )

        # Investment area
        all_areas = sorted(df["Investment area"].dropna().unique())
        sel_area = st.multiselect("Investment Area", options=all_areas, default=[])

        # Enabled for
        all_enabled = sorted([e for e in df["Enabled for"].dropna().unique() if e])
        sel_enabled = st.multiselect("Enabled For", options=all_enabled, default=[])

        # GA Date range
        use_date_filter = st.checkbox("Filter by GA Date")
        date_start = date_end = None
        if use_date_filter:
            dcols = st.columns(2)
            with dcols[0]:
                date_start = st.date_input("From", value=pd.Timestamp.now().date())
            with dcols[1]:
                date_end = st.date_input(
                    "To",
                    value=(pd.Timestamp.now() + timedelta(days=180)).date()
                )

        st.divider()

        # Saved Views
        if db_available() and user_id != "demo":
            st.subheader("💾 Saved Views")
            saved_views = get_saved_views(user_id)

            if saved_views:
                view_names = ["(current filters)"] + [
                    f"{'🌐 ' if v['is_shared'] else ''}{v['name']}"
                    for v in saved_views
                ]
                selected_view = st.selectbox("Load View", view_names)

                if selected_view != "(current filters)":
                    idx = view_names.index(selected_view) - 1
                    view = saved_views[idx]
                    cfg = view["config"]
                    # We display config info — actual filter application
                    # requires rerun with session state, kept simple here
                    st.caption(f"Filters: {json.dumps(cfg, indent=2)[:200]}")

                    if st.button("🗑️ Delete View", key="del_view"):
                        delete_saved_view(view["id"])
                        st.rerun()

            # Save current view
            with st.expander("Save Current View"):
                view_name = st.text_input("View Name")
                view_desc = st.text_input("Description (optional)")
                view_shared = st.checkbox("Share with team")
                if st.button("💾 Save"):
                    if view_name:
                        config = {
                            "products": sel_product,
                            "statuses": sel_status,
                            "waves": sel_wave,
                            "areas": sel_area,
                            "enabled_for": sel_enabled,
                            "search": search,
                        }
                        if save_view(user_id, view_name, view_desc,
                                    config, view_shared):
                            st.success("View saved!")
                            st.rerun()
                        else:
                            st.error("Failed to save view")
                    else:
                        st.warning("Enter a name")

    # Build active filters dict
    current_filters = {
        "products": sel_product,
        "statuses": sel_status,
        "waves": sel_wave,
        "areas": sel_area,
        "enabled_for": sel_enabled,
        "search": search,
    }
    if use_date_filter and date_start and date_end:
        current_filters["date_start"] = date_start
        current_filters["date_end"] = date_end

    # Apply filters
    filtered = apply_filters(df, current_filters)

    # ── Key Metrics ──────────────────────────────
    st.markdown(f"### 📊 {len(filtered):,} of {len(df):,} features")

    metric_cols = st.columns(6)
    status_counts = filtered["Status"].value_counts()

    for i, (status, emoji) in enumerate(zip(
        ["Generally Available", "Public Preview", "Early Access", "Planned"],
        ["🟢", "🔵", "🟣", "⚪"]
    )):
        count = status_counts.get(status, 0)
        pct = (count / len(filtered) * 100) if len(filtered) > 0 else 0
        metric_cols[i].metric(f"{emoji} {status}", f"{count:,}", f"{pct:.0f}%")

    upcoming_30 = len(filtered[
        (filtered["Days to GA"].notna()) &
        (filtered["Days to GA"] >= 0) &
        (filtered["Days to GA"] <= 30)
    ])
    metric_cols[4].metric("🎯 GA in 30d", upcoming_30)

    changed_count = len(
        set(filtered["Release Plan ID"]) &
        st.session_state.get("changed_feature_ids", set())
    )
    metric_cols[5].metric("🔔 Changed (14d)", changed_count)

    st.divider()

    # ── Main Tabs ────────────────────────────────
    tab_overview, tab_features, tab_enablement, tab_watchlist, tab_changes, tab_status = st.tabs([
        "📈 Overview",
        "📋 All Features",
        "⚙️ Enablement",
        "⭐ Watchlist",
        "🔔 Changes",
        "📊 By Status",
    ])

    # ══════════════════════════════════════════════
    # TAB: OVERVIEW
    # ══════════════════════════════════════════════
    with tab_overview:
        st.subheader("Release Pipeline")

        ov_cols = st.columns([2, 1])

        with ov_cols[0]:
            upcoming = filtered[
                (filtered["GA date"].notna()) &
                (filtered["GA date"] >= pd.Timestamp.now().normalize())
            ].copy()

            if not upcoming.empty:
                upcoming["Month"] = upcoming["GA date"].dt.to_period("M").astype(str)
                monthly = upcoming.groupby(["Month", "Status"]).size().reset_index(name="Count")

                fig = px.bar(
                    monthly, x="Month", y="Count", color="Status",
                    title="Upcoming Releases by Month",
                    height=400, color_discrete_map=STATUS_COLORS, barmode="stack"
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No upcoming releases with GA dates in current filters")

        with ov_cols[1]:
            status_dist = filtered["Status"].value_counts().reset_index()
            status_dist.columns = ["Status", "Count"]
            fig_pie = px.pie(
                status_dist, values="Count", names="Status",
                title="Status Distribution", height=400,
                color="Status", color_discrete_map=STATUS_COLORS
            )
            st.plotly_chart(fig_pie, use_container_width=True)

        st.divider()

        # Next 90 days
        st.subheader("Next 90 Days")
        today = pd.Timestamp.now().normalize()
        future_90 = today + timedelta(days=90)
        upcoming_90 = filtered[
            (filtered["GA date"].notna()) &
            (filtered["GA date"] > today) &
            (filtered["GA date"] <= future_90)
        ].sort_values("GA date")

        if not upcoming_90.empty:
            upcoming_90_display = upcoming_90.copy()
            upcoming_90_display["Month"] = upcoming_90_display["GA date"].dt.strftime("%Y-%m (%B)")
            monthly_product = upcoming_90_display.groupby(
                ["Month", "Product name"]
            ).size().reset_index(name="Count")

            fig_prod = px.bar(
                monthly_product, x="Month", y="Count", color="Product name",
                title="Planned GA by Product (Next 90 Days)",
                height=400, text="Count"
            )
            fig_prod.update_traces(textposition="outside")
            st.plotly_chart(fig_prod, use_container_width=True)

            with st.expander(f"📋 View {len(upcoming_90)} Upcoming Features"):
                st.dataframe(
                    upcoming_90[["Product name", "Feature name", "GA date",
                                "Days to GA", "Status", "Release Wave"]],
                    use_container_width=True, hide_index=True
                )
        else:
            st.info("No GA releases in the next 90 days for current filters")

        # Products summary
        st.divider()
        st.subheader("Features by Product")

        product_status = filtered.groupby(
            ["Product name", "Status"]
        ).size().reset_index(name="Count")

        if not product_status.empty:
            fig_ps = px.bar(
                product_status, x="Product name", y="Count",
                color="Status", barmode="stack",
                color_discrete_map=STATUS_COLORS,
                height=500, title="Feature Status by Product"
            )
            fig_ps.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig_ps, use_container_width=True)

    # ══════════════════════════════════════════════
    # TAB: ALL FEATURES
    # ══════════════════════════════════════════════
    with tab_features:
        st.subheader("All Features")

        display_cols = [
            "Product name", "Feature name", "Status",
            "GA date", "Public preview date", "Early access date",
            "GA Release Wave", "Investment area", "Enabled for",
            "Days to GA", "Last Gitcommit date", "Search Link"
        ]

        # View mode toggle
        view_mode = st.radio(
            "View", ["Table", "Cards"], horizontal=True, label_visibility="collapsed"
        )

        if view_mode == "Table":
            event = st.dataframe(
                filtered[display_cols],
                column_config={
                    "Product name": st.column_config.TextColumn("Product", width="medium"),
                    "Feature name": st.column_config.TextColumn("Feature", width="large"),
                    "Status": st.column_config.TextColumn("Status"),
                    "GA date": st.column_config.DateColumn("GA Date", format="YYYY-MM-DD"),
                    "Public preview date": st.column_config.DateColumn("Preview", format="YYYY-MM-DD"),
                    "Early access date": st.column_config.DateColumn("Early Access", format="YYYY-MM-DD"),
                    "GA Release Wave": st.column_config.TextColumn("Wave"),
                    "Investment area": st.column_config.TextColumn("Area"),
                    "Enabled for": st.column_config.TextColumn("Enabled For"),
                    "Days to GA": st.column_config.NumberColumn("Days to GA", format="%d"),
                    "Last Gitcommit date": st.column_config.DateColumn("Updated", format="YYYY-MM-DD"),
                    "Search Link": st.column_config.LinkColumn("🔍", display_text="🔍"),
                },
                use_container_width=True, hide_index=True,
                on_select="rerun", selection_mode="single-row",
                height=600
            )

            # Feature detail on selection
            selected = event.selection.get("rows", [])
            if selected:
                row = filtered.iloc[selected[0]]
                render_feature_card(row, user_id, watchlist_ids)

            # Download
            st.download_button(
                "📥 Download CSV",
                filtered.to_csv(index=False),
                file_name=f"d365_releases_{datetime.now():%Y%m%d}.csv",
                mime="text/csv"
            )

        else:
            # Card view — paginated
            page_size = 20
            total_pages = max(1, (len(filtered) - 1) // page_size + 1)
            page = st.number_input("Page", 1, total_pages, 1)
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size

            st.caption(f"Showing {start_idx + 1}–{min(end_idx, len(filtered))} of {len(filtered)}")

            for _, row in filtered.iloc[start_idx:end_idx].iterrows():
                render_feature_card(row, user_id, watchlist_ids)

    # ══════════════════════════════════════════════
    # TAB: ENABLEMENT
    # ══════════════════════════════════════════════
    with tab_enablement:
        st.subheader("⚙️ Feature Enablement Analysis")

        st.info("""
        **Microsoft's Enablement Categories:**
        - **Users, automatically** — Deploys immediately at GA, affects all users
        - **Admins, makers, marketers, or analysts, automatically** — Auto-deploys for admin/maker roles
        - **Users by admins, makers, or analysts** — Requires manual enablement
        """)

        en_tabs = st.tabs([
            "🔴 Users, automatically",
            "🟠 Admins, auto",
            "🟡 By admins/makers",
            "📊 Summary"
        ])

        # Users, automatically
        with en_tabs[0]:
            st.warning("⚠️ These features deploy automatically when GA date passes.")

            auto_users = filtered[filtered["Enabled for"] == "Users, automatically"].copy()

            if not auto_users.empty:
                upcoming_auto = auto_users[
                    (auto_users["GA date"].notna()) &
                    (auto_users["GA date"] >= pd.Timestamp.now().normalize())
                ].sort_values("GA date")

                already = auto_users[
                    (auto_users["GA date"].notna()) &
                    (auto_users["GA date"] < pd.Timestamp.now().normalize())
                ]

                cols = st.columns(3)
                cols[0].metric("Total", len(auto_users))
                cols[1].metric("🚨 Coming Soon", len(upcoming_auto))
                cols[2].metric("✅ Already Deployed", len(already))

                if not upcoming_auto.empty:
                    st.markdown("#### Upcoming Auto-Enabled")
                    upcoming_auto_display = upcoming_auto.copy()
                    upcoming_auto_display["Month"] = upcoming_auto_display["GA date"].dt.strftime("%Y-%m")
                    monthly = upcoming_auto_display.groupby("Month").size().reset_index(name="Count")

                    fig = px.bar(monthly, x="Month", y="Count",
                                title="Auto-Enabled Features by Month",
                                color_discrete_sequence=["#dc3545"])
                    st.plotly_chart(fig, use_container_width=True)

                    for _, row in upcoming_auto.iterrows():
                        render_feature_card(row, user_id, watchlist_ids)
            else:
                st.success("No auto-enabled features in current filters")

        # Admins, auto
        with en_tabs[1]:
            auto_admins = filtered[
                filtered["Enabled for"] == "Admins, makers, marketers, or analysts, automatically"
            ].copy()

            if not auto_admins.empty:
                st.metric("Total", len(auto_admins))
                upcoming = auto_admins[
                    (auto_admins["GA date"].notna()) &
                    (auto_admins["GA date"] >= pd.Timestamp.now().normalize())
                ].sort_values("GA date")

                if not upcoming.empty:
                    for _, row in upcoming.iterrows():
                        render_feature_card(row, user_id, watchlist_ids)
                else:
                    st.info("No upcoming features in this category")
            else:
                st.info("No features in this category")

        # By admins/makers
        with en_tabs[2]:
            st.success("✅ You control when these features are enabled.")

            admin_ctrl = filtered[
                filtered["Enabled for"] == "Users by admins, makers, or analysts"
            ].copy()

            if not admin_ctrl.empty:
                available = admin_ctrl[admin_ctrl["Status"] == "Generally Available"]
                coming = admin_ctrl[admin_ctrl["Status"] != "Generally Available"]

                cols = st.columns(3)
                cols[0].metric("Total", len(admin_ctrl))
                cols[1].metric("Available to Enable", len(available))
                cols[2].metric("Coming Soon", len(coming))

                if not available.empty:
                    st.markdown("#### Ready for Enablement")
                    st.dataframe(
                        available[["Product name", "Feature name", "GA date",
                                  "Release Wave", "Search Link"]],
                        column_config={
                            "GA date": st.column_config.DateColumn("GA", format="YYYY-MM-DD"),
                            "Search Link": st.column_config.LinkColumn("🔍", display_text="🔍"),
                        },
                        use_container_width=True, hide_index=True, height=400
                    )
            else:
                st.info("No features in this category")

        # Summary
        with en_tabs[3]:
            enablement_summary = filtered["Enabled for"].fillna("Not specified").value_counts().reset_index()
            enablement_summary.columns = ["Enablement Type", "Count"]
            enablement_summary["Short"] = enablement_summary["Enablement Type"].apply(
                lambda x: "🔴 Users, auto" if x == "Users, automatically"
                else ("🟠 Admins, auto" if "automatically" in x
                else ("🟡 By admins" if "by admins" in x.lower()
                else "⚪ Not specified"))
            )
            fig = px.pie(
                enablement_summary, values="Count", names="Short",
                title="Features by Enablement Type",
                color_discrete_sequence=["#dc3545", "#fd7e14", "#ffc107", "#6c757d"]
            )
            st.plotly_chart(fig, use_container_width=True)

    # ══════════════════════════════════════════════
    # TAB: WATCHLIST
    # ══════════════════════════════════════════════
    with tab_watchlist:
        st.subheader("⭐ My Watchlist")

        if user_id == "demo" or not db_available():
            st.info(
                "Watchlist requires database connection. "
                "Configure Supabase in .streamlit/secrets.toml to enable."
            )
        else:
            watchlist_details = get_watchlist_details(user_id)

            if watchlist_details:
                st.metric("Tracked Features", len(watchlist_details))

                # Match watchlist items with current data
                for wl_item in watchlist_details:
                    rpid = wl_item["release_plan_id"]
                    match = filtered[filtered["Release Plan ID"] == rpid]

                    if match.empty:
                        # Feature not in current filter but still on watchlist
                        match = df[df["Release Plan ID"] == rpid]

                    if not match.empty:
                        row = match.iloc[0]
                        render_feature_card(row, user_id, watchlist_ids)
                    else:
                        # Feature no longer in data
                        st.warning(
                            f"**{wl_item['feature_name']}** ({wl_item['product_name']}) "
                            "— Feature not found in current data"
                        )
                        if st.button(f"Remove", key=f"rm_orphan_{rpid}"):
                            remove_from_watchlist(user_id, rpid)
                            st.rerun()
            else:
                st.info(
                    "Your watchlist is empty. Browse features in the "
                    "**All Features** tab and click ☆ to start tracking."
                )

    # ══════════════════════════════════════════════
    # TAB: CHANGES
    # ══════════════════════════════════════════════
    with tab_changes:
        st.subheader("🔔 Change Detection")

        if not db_available():
            st.info(
                "Change detection requires database. "
                "Configure Supabase to enable tracking."
            )
            st.markdown("""
            **How it works:**
            1. Each time you click **🔄 Refresh & Detect Changes**, the app fetches fresh data
            2. It compares every feature against the last stored snapshot
            3. Changes in dates, descriptions, waves, etc. are logged
            4. Changed features get a 🔔 badge throughout the UI
            """)
        else:
            change_period = st.selectbox(
                "Show changes from",
                [(7, "Last 7 days"), (14, "Last 14 days"),
                 (30, "Last 30 days"), (60, "Last 60 days")],
                format_func=lambda x: x[1],
                index=1
            )

            changes = get_recent_changes(days=change_period[0])

            if changes:
                st.metric("Total Changes", len(changes))

                # Group by type
                change_types = {}
                for c in changes:
                    ct = c["change_type"]
                    change_types[ct] = change_types.get(ct, 0) + 1

                type_cols = st.columns(len(change_types))
                for i, (ct, count) in enumerate(sorted(change_types.items())):
                    label = CHANGE_TYPE_LABELS.get(ct, ct)
                    type_cols[i].metric(label, count)

                st.divider()

                # Change log table
                change_df = pd.DataFrame(changes)
                change_df["Type"] = change_df["change_type"].map(
                    lambda x: CHANGE_TYPE_LABELS.get(x, x)
                )
                change_df["Detected"] = pd.to_datetime(
                    change_df["detected_at"]
                ).dt.strftime("%Y-%m-%d %H:%M")

                st.dataframe(
                    change_df[[
                        "Detected", "Type", "product_name",
                        "feature_name", "field_changed",
                        "old_value", "new_value"
                    ]].rename(columns={
                        "product_name": "Product",
                        "feature_name": "Feature",
                        "field_changed": "Field",
                        "old_value": "Old Value",
                        "new_value": "New Value",
                    }),
                    use_container_width=True, hide_index=True, height=500
                )

                st.download_button(
                    "📥 Download Change Log",
                    change_df.to_csv(index=False),
                    file_name=f"change_log_{datetime.now():%Y%m%d}.csv",
                    mime="text/csv"
                )
            else:
                st.info(
                    f"No changes detected in the last {change_period[0]} days. "
                    "Click **🔄 Refresh & Detect Changes** to check for updates."
                )

    # ══════════════════════════════════════════════
    # TAB: BY STATUS
    # ══════════════════════════════════════════════
    with tab_status:
        st.subheader("Features by Status")

        status_cols = st.columns(4)
        for i, (status, emoji) in enumerate(zip(
            ["Generally Available", "Public Preview", "Early Access", "Planned"],
            ["🟢", "🔵", "🟣", "⚪"]
        )):
            with status_cols[i]:
                sf = filtered[filtered["Status"] == status]
                st.markdown(f"### {emoji} {status}")
                st.metric("Count", len(sf))
                if not sf.empty:
                    with st.expander(f"View {len(sf)} features"):
                        st.dataframe(
                            sf[["Product name", "Feature name", "GA date",
                                "Public preview date", "Release Wave"]],
                            column_config={
                                "GA date": st.column_config.DateColumn("GA", format="YYYY-MM-DD"),
                                "Public preview date": st.column_config.DateColumn("Preview", format="YYYY-MM-DD"),
                            },
                            use_container_width=True, hide_index=True, height=300
                        )

        st.divider()

        # Early Access features
        st.subheader("🟣 Early Access Features")
        ea = filtered[filtered["Status"] == "Early Access"]
        if not ea.empty:
            st.info(
                f"**{len(ea)} features** in early access. "
                "[Opt-in guide](https://learn.microsoft.com/en-us/power-platform/admin/opt-in-early-access-updates)"
            )
            for _, row in ea.iterrows():
                render_feature_card(row, user_id, watchlist_ids)
        else:
            st.info("No features currently in early access")

    # ── Footer ───────────────────────────────────
    st.divider()
    db_status = "🟢 Connected" if db_available() else "⚪ Demo Mode (no persistence)"
    st.caption(
        f"Data: [Microsoft Release Plans](https://releaseplans.microsoft.com) | "
        f"DB: {db_status} | "
        f"Status derived from dates"
    )


# ────────────────────────────────────────────────
# RUN
# ────────────────────────────────────────────────
if __name__ == "__main__":
    main()