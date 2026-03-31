"""Main portfolio home page showing holdings, watchlist, and allocation views."""

import streamlit as st
import sys
import os
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from src.io import ensure_data_files, load_transactions, load_watchlist
from src.fifo import run_fifo
from src.metrics import calculate_metrics, portfolio_allocation, portfolio_value_and_cost_over_time
from src.pricing import get_latest_prices, get_ticker_profiles
from src.ui import apply_app_chrome, render_data_table, render_page_header

apply_app_chrome("Dashboard")
st_autorefresh(interval = 120_000, key="price_refresh")  # refresh every 2 minutes to update prices

ensure_data_files()
render_page_header(
    "Dashboard",
    "A cleaner view of your portfolio across holdings, dividends, and cost basis trends.",
    kicker="Home",
)

# ---------- LOAD DATA ----------
df = load_transactions()

# ---------- RUN FIFO ----------
portfolio, _, dividends = run_fifo(df)
summary = calculate_metrics(portfolio)
watchlist_df = load_watchlist()

if not summary.empty:
    # Merge metadata here so one holdings table can support both equities and ETFs.
    holding_profiles = get_ticker_profiles(tuple(summary["Ticker"].tolist()))
    summary = summary.merge(holding_profiles, on="Ticker", how="left")
    summary["Sector / Fund Category (ETFs)"] = summary.apply(
        lambda row: row["Fund Category"] if row.get("Type") in {"ETF", "MUTUALFUND"} else row["Sector"],
        axis=1,
    )
    summary["Industry / Fund Family (ETFs)"] = summary.apply(
        lambda row: row["Fund Family"] if row.get("Type") in {"ETF", "MUTUALFUND"} else row["Industry"],
        axis=1,
    )
    summary["Type"] = summary["Type"].replace("", "Unknown")
    summary["Sector / Fund Category (ETFs)"] = summary["Sector / Fund Category (ETFs)"].replace("", "Unknown")
    summary["Industry / Fund Family (ETFs)"] = summary["Industry / Fund Family (ETFs)"].replace("", "Unknown")

total_cost = summary["Cost Basis"].sum()
total_equity = summary["Equity"].sum()
total_pl = total_equity - total_cost
total_pl_pct = (total_pl/total_cost) * 100 if total_cost != 0 else 0
total_dividends = sum(dividends.values())

# ---------- DISPLAY KEY METRICS ----------
st.subheader("Portfolio Overview")

# Row 1 (most important)
c1, c2, c3 = st.columns(3)
c1.metric("Total Invested", f"${total_cost:,.2f}")
c2.metric("Total Equity", f"${total_equity:,.2f}")
c3.metric("Total P/L", f"${total_pl:,.2f}", f"{total_pl_pct:.2f}%")

# Row 2 (supporting)
c4, c5 = st.columns(2)
c4.metric("Positions", str(len(summary)))
c5.metric("Dividends (lifetime)", f"${total_dividends:,.2f}")
# ---------- DISPLAY HOLDINGS ----------
st.subheader("📈 Current Holdings")
render_data_table(
    summary[
        [
            "Ticker",
            "Name",
            "Type",
            "Sector / Fund Category (ETFs)",
            "Industry / Fund Family (ETFs)",
            "Shares",
            "Average Cost",
            "Cost Basis",
            "Current Price",
            "Equity",
            "Unrealised P/L",
            "Unrealised %",
        ]
    ],
    hide_index=True,
)

if not watchlist_df.empty:
    st.subheader("Watchlist Snapshot")
    watch_prices = get_latest_prices(watchlist_df["Ticker"].tolist())
    watch_snapshot = watchlist_df.copy()
    watch_snapshot["Current Price"] = watch_snapshot["Ticker"].map(watch_prices).fillna(0.0)
    watch_snapshot["Gap to Target"] = watch_snapshot["Current Price"] - watch_snapshot["Target Price"]
    # Watchlist status is derived from live price vs target rather than stored manually.
    watch_snapshot["Status"] = watch_snapshot.apply(
        lambda row: "No Price"
        if row["Current Price"] <= 0
        else (
            "Ready"
            if (
                row["Current Price"] >= row["Target Price"]
                if row["Watch Type"] == "Sell"
                else row["Current Price"] <= row["Target Price"]
            )
            else "Watching"
        ),
        axis=1,
    )

    w1, w2 = st.columns(2)
    w1.metric("Watchlist Items", str(len(watch_snapshot)))
    w2.metric("At or Below Target", str(int((watch_snapshot["Status"] == "Ready").sum())))

    render_data_table(
        watch_snapshot[
            [
                "Ticker",
                "Watch Type",
                "Target Price",
                "Current Price",
                "Fair Value",
                "Gap to Target",
                "Priority",
                "Status",
                "Notes",
            ]
        ].sort_values(["Status", "Gap to Target", "Priority"]),
        hide_index=True,
    )

# ---------- STOCK DETAILS ----------
ticker = st.selectbox(
    "View Stock Details",
    summary["Ticker"].unique()
)

if st.button("Open Stock Page"):
    st.session_state["selected_ticker"] = ticker
    st.switch_page("pages/1_Stock_Details.py")

# ---------- DISPLAY PORTFOLIO VALUE AND COST OVER TIME ----------
st.subheader("💰 Portfolio Value vs Total Cost")

ts = portfolio_value_and_cost_over_time(df)

if not ts.empty:
    ts = ts.reset_index().rename(columns={"index": "Date"})
    ts_fig = go.Figure()
    ts_fig.add_trace(
        go.Scatter(
            x=ts["Date"],
            y=ts["Total Cost"],
            mode="lines",
            name="Total Cost",
            line=dict(color="#9b7655", width=3),
        )
    )
    ts_fig.add_trace(
        go.Scatter(
            x=ts["Date"],
            y=ts["Portfolio Value"],
            mode="lines",
            name="Portfolio Value",
            line=dict(color="#3f7cac", width=3),
        )
    )
    ts_fig.update_layout(
        height=420,
        paper_bgcolor="rgba(255,253,249,0)",
        plot_bgcolor="rgba(255,253,249,0)",
        margin=dict(t=40, r=30, b=40, l=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        xaxis_title="Date",
        yaxis_title="Value",
    )
    st.plotly_chart(ts_fig, use_container_width=True)
else:
    st.info("Not enough trade data yet to plot.")
# ---------- DISPLAY PORTFOLIO ALLOCATION ----------
st.subheader("Portfolio Allocation")

alloc_df = portfolio_allocation(portfolio)

def build_allocation_pie(
    dataframe,
    names_col: str,
    values_col: str = "Value",
    title: str = "",
    show_slice_text: bool = True,
):
    """Create a donut chart with lighter labeling for dense allocation groupings."""
    fig = px.pie(
        dataframe,
        values=values_col,
        names=names_col,
        hole=0.4,
    )
    dense_chart = len(dataframe) > 6
    fig.update_traces(
        textinfo="none" if not show_slice_text else ("percent" if dense_chart else "percent+label"),
        textposition="inside" if not dense_chart else "outside",
        hovertemplate=f"%{{label}}<br>%{{value:,.2f}}<br>%{{percent}}<extra></extra>",
    )
    fig.update_layout(
        title=title,
        paper_bgcolor="rgba(255,253,249,0)",
        plot_bgcolor="rgba(255,253,249,0)",
        margin=dict(t=60 if title else 30, r=30, b=50, l=30),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.30,
            xanchor="left",
            x=0,
            font=dict(size=11),
        ),
    )
    return fig


def collapse_small_slices(dataframe, names_col: str, values_col: str = "Value", keep_top: int = 6):
    """Group the smallest categories into `Other` to keep pies readable."""
    if len(dataframe) <= keep_top:
        return dataframe

    ranked = dataframe.sort_values(values_col, ascending=False).reset_index(drop=True)
    top = ranked.head(keep_top).copy()
    remainder = ranked.iloc[keep_top:]

    if remainder.empty:
        return top

    other_value = remainder[values_col].sum()
    other_row = pd.DataFrame([{names_col: "Other", values_col: other_value}])
    return pd.concat([top, other_row], ignore_index=True)

if not alloc_df.empty:
    ticker_alloc = collapse_small_slices(alloc_df, "Ticker", keep_top=8)
    c1, c2 = st.columns(2)
    c1.plotly_chart(
        build_allocation_pie(
            ticker_alloc,
            "Ticker",
            title="By Ticker",
            show_slice_text=False,
        ),
        use_container_width=True,
    )

    type_alloc = (
        summary.groupby("Type", as_index=False)["Equity"]
        .sum()
        .rename(columns={"Equity": "Value"})
        .sort_values("Value", ascending=False)
    )
    c2.plotly_chart(
        build_allocation_pie(type_alloc, "Type", title="By Type"),
        use_container_width=True,
    )

    c3, c4 = st.columns(2)
    sector_alloc = (
        summary.groupby("Sector / Fund Category (ETFs)", as_index=False)["Equity"]
        .sum()
        .rename(columns={"Equity": "Value"})
        .sort_values("Value", ascending=False)
    )
    sector_alloc = collapse_small_slices(sector_alloc, "Sector / Fund Category (ETFs)")
    c3.plotly_chart(
        build_allocation_pie(sector_alloc, "Sector / Fund Category (ETFs)", title="By Sector / Fund Category"),
        use_container_width=True,
    )

    industry_alloc = (
        summary.groupby("Industry / Fund Family (ETFs)", as_index=False)["Equity"]
        .sum()
        .rename(columns={"Equity": "Value"})
        .sort_values("Value", ascending=False)
    )
    industry_alloc = collapse_small_slices(industry_alloc, "Industry / Fund Family (ETFs)")
    c4.plotly_chart(
        build_allocation_pie(
            industry_alloc,
            "Industry / Fund Family (ETFs)",
            title="By Industry / Fund Family",
            show_slice_text=False,
        ),
        use_container_width=True,
    )
else:
    st.info("No current holdings yet to calculate allocation.")
