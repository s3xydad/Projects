"""Streamlit dashboard — Telecom Social Monitor.

Run:
  cd telecom-monitor
  streamlit run dashboard/app.py

7 panels:
  1. Overview          — post counts + sentiment donuts per company
  2. Theme Breakdown   — theme distribution per company
  3. Sentiment Trends  — monthly line chart per company
  4. Platform Breakdown— volume/sentiment by platform per company
  5. Flagged Content   — LEGAL and HATE_SPEECH tables
  6. Raw Data Explorer — searchable/sortable table + CSV/JSON export
  7. Language          — language pie chart + sentiment per language
"""

import json
import io
import sqlite3
from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import config

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Telecom Social Monitor",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

COMPANY_COLORS = {"ATT": "#00A8E0", "TMOBILE": "#E20074", "VERIZON": "#CD040B"}
SENT_COLORS    = {"POSITIVE": "#2ECC71", "NEUTRAL": "#95A5A6", "NEGATIVE": "#E74C3C"}
PLATFORM_COLORS= {"reddit": "#FF4500", "twitter": "#1DA1F2", "facebook": "#1877F2"}
COMPANIES      = ["ATT", "TMOBILE", "VERIZON"]
THEMES         = ["CUSTOMER_SERVICE", "PRICING_BILLING", "NETWORK_COVERAGE",
                  "CONTRACT_CANCELLATION", "OTHER"]

# ── Data loading ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=120)
def load_data() -> pd.DataFrame:
    try:
        conn = sqlite3.connect(config.DB_PATH)
        df = pd.read_sql_query("SELECT * FROM posts", conn)
        conn.close()
    except Exception as exc:
        st.error(f"Could not load database at '{config.DB_PATH}': {exc}")
        return pd.DataFrame()

    if df.empty:
        return df

    df["companies"] = df["companies"].apply(
        lambda x: json.loads(x) if isinstance(x, str) else []
    )
    df["themes"] = df["themes"].apply(
        lambda x: json.loads(x) if isinstance(x, str) else []
    )
    df["published_at"] = pd.to_datetime(df["published_at"], utc=True, errors="coerce")
    df["month"] = df["published_at"].dt.to_period("M").astype(str)
    return df


def explode_companies(df: pd.DataFrame) -> pd.DataFrame:
    """Explode so each (post, company) pair is its own row."""
    return df.explode("companies").rename(columns={"companies": "company"})


def explode_themes(df: pd.DataFrame) -> pd.DataFrame:
    return df.explode("themes").rename(columns={"themes": "theme"})


# ── Sidebar filters ───────────────────────────────────────────────────────────

def sidebar_filters(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.header("Filters")

    companies = st.sidebar.multiselect(
        "Company", COMPANIES, default=COMPANIES, key="filter_company"
    )
    platforms = st.sidebar.multiselect(
        "Platform", ["reddit", "twitter", "facebook"],
        default=["reddit", "twitter", "facebook"], key="filter_platform"
    )
    themes = st.sidebar.multiselect(
        "Theme", THEMES, default=THEMES, key="filter_theme"
    )
    sentiments = st.sidebar.multiselect(
        "Sentiment", ["POSITIVE", "NEUTRAL", "NEGATIVE"],
        default=["POSITIVE", "NEUTRAL", "NEGATIVE"], key="filter_sentiment"
    )

    date_min = df["published_at"].min()
    date_max = df["published_at"].max()
    if pd.isna(date_min):
        date_min = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=730)
    if pd.isna(date_max):
        date_max = pd.Timestamp.now(tz="UTC")

    date_range = st.sidebar.date_input(
        "Date range",
        value=(date_min.date(), date_max.date()),
        min_value=date_min.date(),
        max_value=date_max.date(),
        key="filter_dates",
    )
    start_date = pd.Timestamp(date_range[0], tz="UTC")
    end_date   = pd.Timestamp(date_range[1], tz="UTC") + pd.Timedelta(days=1)

    langs = ["(all)"] + sorted(df["detected_language"].dropna().unique().tolist())
    sel_lang = st.sidebar.selectbox("Language", langs, key="filter_lang")

    # Apply filters
    mask = (
        df["platform"].isin(platforms) &
        df["sentiment_label"].isin(sentiments) &
        (df["published_at"] >= start_date) &
        (df["published_at"] <= end_date)
    )
    if sel_lang != "(all)":
        mask &= (df["detected_language"] == sel_lang)

    # Company and theme filters need exploded logic
    df_filtered = df[mask].copy()
    df_filtered = df_filtered[
        df_filtered["companies"].apply(lambda cs: any(c in companies for c in cs))
    ]
    df_filtered = df_filtered[
        df_filtered["themes"].apply(lambda ts: any(t in themes for t in ts))
    ]
    return df_filtered


# ── Panel 1: Overview ─────────────────────────────────────────────────────────

def panel_overview(df: pd.DataFrame) -> None:
    st.header("1. Overview")
    if df.empty:
        st.info("No data — run the pipeline or use --demo to seed the database.")
        return

    df_co = explode_companies(df)
    df_co = df_co[df_co["company"].isin(COMPANIES)]

    # Post counts
    counts = df_co.groupby("company").size().reset_index(name="count")
    col1, col2, col3 = st.columns(3)
    for col, company in zip([col1, col2, col3], COMPANIES):
        cnt = counts[counts["company"] == company]["count"].sum()
        label = company.replace("ATT", "AT&T").replace("TMOBILE", "T-Mobile")
        col.metric(label, f"{cnt:,}")

    st.subheader("Sentiment breakdown per company")
    sent_co = (
        df_co.groupby(["company", "sentiment_label"])
        .size()
        .reset_index(name="count")
    )

    cols = st.columns(3)
    for col, company in zip(cols, COMPANIES):
        sub = sent_co[sent_co["company"] == company]
        label = company.replace("ATT", "AT&T").replace("TMOBILE", "T-Mobile")
        if sub.empty:
            col.write(f"No data for {label}")
            continue
        fig = px.pie(
            sub, names="sentiment_label", values="count",
            color="sentiment_label", color_discrete_map=SENT_COLORS,
            title=label, hole=0.45,
        )
        fig.update_layout(margin=dict(t=40, b=0, l=0, r=0), height=280,
                          showlegend=True, legend=dict(orientation="h"))
        col.plotly_chart(fig, use_container_width=True)

    # Side-by-side stacked bar
    st.subheader("Side-by-side comparison")
    pivot = sent_co.pivot(index="company", columns="sentiment_label", values="count").fillna(0)
    pivot = pivot.reset_index()
    fig2 = go.Figure()
    for sent in ["POSITIVE", "NEUTRAL", "NEGATIVE"]:
        if sent in pivot.columns:
            fig2.add_trace(go.Bar(
                name=sent, x=pivot["company"], y=pivot[sent],
                marker_color=SENT_COLORS[sent],
            ))
    fig2.update_layout(barmode="stack", height=350, xaxis_title="Company",
                       yaxis_title="Posts", legend_title="Sentiment")
    st.plotly_chart(fig2, use_container_width=True)


# ── Panel 2: Theme Breakdown ──────────────────────────────────────────────────

def panel_themes(df: pd.DataFrame) -> None:
    st.header("2. Theme Breakdown")
    if df.empty:
        st.info("No data available.")
        return

    df_co = explode_companies(df)
    df_co = df_co[df_co["company"].isin(COMPANIES)]
    df_co_th = explode_themes(df_co)

    theme_filter = st.multiselect(
        "Filter by theme", THEMES, default=THEMES, key="theme_panel_filter"
    )
    df_co_th = df_co_th[df_co_th["theme"].isin(theme_filter)]

    grouped = df_co_th.groupby(["company", "theme"]).size().reset_index(name="count")

    fig = px.bar(
        grouped, x="theme", y="count", color="company",
        barmode="group", color_discrete_map=COMPANY_COLORS,
        labels={"theme": "Theme", "count": "Posts", "company": "Company"},
        height=420,
    )
    fig.update_xaxes(tickangle=-20)
    st.plotly_chart(fig, use_container_width=True)

    # Per-company breakdown
    st.subheader("Per-company theme distribution")
    cols = st.columns(3)
    for col, company in zip(cols, COMPANIES):
        sub = grouped[grouped["company"] == company]
        label = company.replace("ATT", "AT&T").replace("TMOBILE", "T-Mobile")
        if sub.empty:
            col.write(f"No data for {label}")
            continue
        fig2 = px.pie(
            sub, names="theme", values="count",
            title=label, hole=0.3, height=300,
        )
        fig2.update_layout(margin=dict(t=40, b=0, l=0, r=0), showlegend=False)
        col.plotly_chart(fig2, use_container_width=True)


# ── Panel 3: Sentiment Over Time ──────────────────────────────────────────────

def panel_sentiment_time(df: pd.DataFrame) -> None:
    st.header("3. Sentiment Over Time")
    if df.empty:
        st.info("No data available.")
        return

    df_co = explode_companies(df)
    df_co = df_co[df_co["company"].isin(COMPANIES)]

    selected_sentiment = st.radio(
        "Show sentiment", ["POSITIVE", "NEUTRAL", "NEGATIVE"],
        index=0, horizontal=True, key="sent_time_radio"
    )

    sub = df_co[df_co["sentiment_label"] == selected_sentiment]
    monthly = (
        sub.groupby(["month", "company"])
        .size()
        .reset_index(name="count")
        .sort_values("month")
    )

    fig = px.line(
        monthly, x="month", y="count", color="company",
        color_discrete_map=COMPANY_COLORS,
        labels={"month": "Month", "count": "Posts", "company": "Company"},
        markers=True, height=450,
    )
    fig.update_layout(xaxis_tickangle=-45, hovermode="x unified")
    # Annotate max spikes
    for company in COMPANIES:
        sub_co = monthly[monthly["company"] == company]
        if sub_co.empty:
            continue
        peak = sub_co.loc[sub_co["count"].idxmax()]
        fig.add_annotation(
            x=peak["month"], y=peak["count"],
            text=f"Peak: {int(peak['count'])}",
            showarrow=True, arrowhead=2, ax=0, ay=-30,
            font=dict(size=10),
        )
    st.plotly_chart(fig, use_container_width=True)


# ── Panel 4: Platform Breakdown ───────────────────────────────────────────────

def panel_platform(df: pd.DataFrame) -> None:
    st.header("4. Platform Breakdown")
    if df.empty:
        st.info("No data available.")
        return

    df_co = explode_companies(df)
    df_co = df_co[df_co["company"].isin(COMPANIES)]

    volume = df_co.groupby(["company", "platform"]).size().reset_index(name="count")
    fig1 = px.bar(
        volume, x="company", y="count", color="platform",
        barmode="group", color_discrete_map=PLATFORM_COLORS,
        labels={"count": "Posts", "company": "Company", "platform": "Platform"},
        title="Post volume by platform per company", height=380,
    )
    st.plotly_chart(fig1, use_container_width=True)

    sent_plat = (
        df_co.groupby(["platform", "sentiment_label"])
        .size()
        .reset_index(name="count")
    )
    fig2 = px.bar(
        sent_plat, x="platform", y="count", color="sentiment_label",
        barmode="stack", color_discrete_map=SENT_COLORS,
        labels={"count": "Posts", "platform": "Platform", "sentiment_label": "Sentiment"},
        title="Sentiment split per platform (all companies)", height=350,
    )
    st.plotly_chart(fig2, use_container_width=True)


# ── Panel 5: Flagged Content ──────────────────────────────────────────────────

def panel_flagged(df: pd.DataFrame) -> None:
    st.header("5. Flagged Content")
    if df.empty:
        st.info("No data available.")
        return

    cols_to_show = [
        "platform", "published_at", "companies", "themes",
        "sentiment_label", "url", "raw_text",
    ]

    def render_flag_table(flag_col: str, label: str) -> None:
        flagged = df[df[flag_col] == 1].copy()
        flagged["raw_text"] = flagged["raw_text"].str[:120] + "…"
        flagged["companies"] = flagged["companies"].apply(lambda x: ", ".join(x))
        flagged["themes"]    = flagged["themes"].apply(lambda x: ", ".join(x))
        flagged["published_at"] = flagged["published_at"].dt.strftime("%Y-%m-%d")

        st.subheader(f"{label} ({len(flagged):,} posts)")
        if flagged.empty:
            st.success(f"No {label.lower()} posts found.")
            return

        search = st.text_input(f"Search {label}", key=f"search_{flag_col}")
        if search:
            mask = flagged["raw_text"].str.contains(search, case=False, na=False)
            flagged = flagged[mask]

        available = [c for c in cols_to_show if c in flagged.columns]
        st.dataframe(
            flagged[available].sort_values("published_at", ascending=False),
            use_container_width=True, height=350,
        )

    render_flag_table("flag_legal", "⚖️ Legal Flags")
    st.divider()
    render_flag_table("flag_hate_speech", "🚫 Hate Speech Flags")


# ── Panel 6: Raw Data Explorer ────────────────────────────────────────────────

def panel_raw_explorer(df: pd.DataFrame) -> None:
    st.header("6. Raw Data Explorer")
    if df.empty:
        st.info("No data available.")
        return

    search = st.text_input("Full-text search", key="raw_search")

    display = df.copy()
    if search:
        mask = (
            display["raw_text"].str.contains(search, case=False, na=False) |
            display.get("translated_text", pd.Series(dtype=str)).str.contains(
                search, case=False, na=False
            )
        )
        display = display[mask]

    display["companies"] = display["companies"].apply(lambda x: ", ".join(x))
    display["themes"]    = display["themes"].apply(lambda x: ", ".join(x))
    display["published_at"] = display["published_at"].dt.strftime("%Y-%m-%dT%H:%M")
    display["raw_text"]  = display["raw_text"].str[:200]

    cols_order = [
        "platform", "published_at", "companies", "themes",
        "sentiment_label", "sentiment_score", "detected_language",
        "engagement_likes", "engagement_comments", "engagement_shares",
        "flag_legal", "flag_hate_speech", "raw_text", "url",
    ]
    cols_order = [c for c in cols_order if c in display.columns]

    st.write(f"{len(display):,} records")
    st.dataframe(
        display[cols_order].sort_values("published_at", ascending=False),
        use_container_width=True, height=450,
    )

    # Export
    st.subheader("Export")
    c1, c2 = st.columns(2)
    csv_data = display[cols_order].to_csv(index=False).encode("utf-8")
    c1.download_button(
        "⬇ Download CSV", csv_data, "telecom_posts.csv", "text/csv",
        key="dl_csv"
    )

    # JSON export uses original (non-truncated) data
    json_df = df.copy()
    json_df["companies"] = json_df["companies"].apply(lambda x: ", ".join(x) if isinstance(x, list) else x)
    json_df["themes"]    = json_df["themes"].apply(lambda x: ", ".join(x) if isinstance(x, list) else x)
    json_df["published_at"] = json_df["published_at"].astype(str)
    json_bytes = json_df.to_json(orient="records", indent=2).encode("utf-8")
    c2.download_button(
        "⬇ Download JSON", json_bytes, "telecom_posts.json", "application/json",
        key="dl_json"
    )


# ── Panel 7: Language Distribution ───────────────────────────────────────────

def panel_language(df: pd.DataFrame) -> None:
    st.header("7. Language Distribution")
    if df.empty:
        st.info("No data available.")
        return

    lang_counts = df["detected_language"].value_counts().reset_index()
    lang_counts.columns = ["language", "count"]

    fig = px.pie(
        lang_counts, names="language", values="count",
        title="Language distribution of all collected posts",
        hole=0.3, height=420,
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Sentiment per language")
    lang_sent = (
        df.groupby(["detected_language", "sentiment_label"])
        .size()
        .reset_index(name="count")
    )
    fig2 = px.bar(
        lang_sent, x="detected_language", y="count", color="sentiment_label",
        barmode="stack", color_discrete_map=SENT_COLORS,
        labels={"detected_language": "Language", "count": "Posts"},
        height=380,
    )
    fig2.update_xaxes(tickangle=-30)
    st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Language table")
    table = lang_counts.copy()
    table["pct"] = (table["count"] / table["count"].sum() * 100).round(2)
    st.dataframe(table, use_container_width=True, height=300)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    st.title("📡 Telecom Social Monitor")
    st.caption(
        "Competitive analysis of public social media posts about AT&T, T-Mobile, and Verizon."
    )

    df_raw = load_data()

    if df_raw.empty:
        st.warning(
            "Database is empty. Run the pipeline to collect data, or use demo mode:\n\n"
            "```\npython pipeline.py --demo\n```\n"
            "Then refresh this page."
        )
        st.stop()

    df = sidebar_filters(df_raw)

    tabs = st.tabs([
        "Overview",
        "Theme Breakdown",
        "Sentiment Over Time",
        "Platform Breakdown",
        "Flagged Content",
        "Raw Data Explorer",
        "Language",
    ])

    with tabs[0]: panel_overview(df)
    with tabs[1]: panel_themes(df)
    with tabs[2]: panel_sentiment_time(df)
    with tabs[3]: panel_platform(df)
    with tabs[4]: panel_flagged(df)
    with tabs[5]: panel_raw_explorer(df)
    with tabs[6]: panel_language(df)

    st.sidebar.divider()
    st.sidebar.caption(
        f"DB: `{config.DB_PATH}` | {len(df):,} posts (filtered) "
        f"/ {len(df_raw):,} total"
    )
    if st.sidebar.button("🔄 Refresh data"):
        st.cache_data.clear()
        st.rerun()


if __name__ == "__main__":
    main()
