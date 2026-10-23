"""Options page: income from option strategies, open positions, and every closed trade."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from src.importers.moomoo import load_sync_state
from src.io import load_options, load_source_transactions
from src.options import priced_option_trades
from src.ui import apply_app_chrome, render_data_table, render_page_header

apply_app_chrome("Options")
render_page_header(
    "Options",
    "Premium earned from option strategies, what's still open, and how each trade ended.",
    kicker="Income",
)

fills = load_options()
if fills.empty:
    st.info("No option trades yet. Run a sync on the Sync Moomoo page to pull them in.")
    st.stop()

trades = priced_option_trades(
    fills,
    load_source_transactions("Trades"),
    load_sync_state().get("option_marks", {}),
)
closed = trades[trades["Outcome"] != "Open"].copy()
open_trades = trades[trades["Outcome"] == "Open"].copy()

realised = closed["P/L"].sum()
open_pl = open_trades["P/L"].sum()
win_rate = (closed["P/L"] > 0).mean() * 100 if not closed.empty else 0.0
collateral_returns = closed["Return on Collateral %"].dropna()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Realised Income", f"${realised:,.2f}")
c2.metric("Open P/L", f"${open_pl:,.2f}" if open_trades["P/L"].notna().all() else "No quote")
c3.metric("Win Rate", f"{win_rate:.0f}%", f"{len(closed)} closed trades", delta_color="off")
c4.metric(
    "Avg Return on Collateral",
    f"{collateral_returns.mean():.2f}%" if not collateral_returns.empty else "—",
)

st.caption(
    "P/L is after all fees, with each contract covering 100 shares. Open positions are valued at "
    "Yahoo Finance's last traded price, or moomoo's price at the last sync when Yahoo has no quote. "
    "Return on collateral applies to short puts: P/L divided by the cash needed if assigned (strike × 100)."
)

st.subheader("Open Positions")
if open_trades.empty:
    st.caption("No open option positions.")
else:
    today = pd.Timestamp.today().normalize()
    open_view = pd.DataFrame({
        "Contract": open_trades["Contract"],
        "Strategy": open_trades["Strategy"],
        "Contracts": open_trades["Open Contracts"],
        "Strike": open_trades["Strike"],
        "Expiry": open_trades["Expiry"],
        "Days Left": (open_trades["Expiry"] - today).dt.days,
        "Opened At": open_trades["Opening Value"] / open_trades["Contracts"] / 100,
        "Current Price": open_trades["Current Price"],
        "Premium (net of fees)": open_trades["Net Cash"],
        "P/L": open_trades["P/L"],
        "Collateral": open_trades["Collateral"],
    })
    render_data_table(open_view, hide_index=True)

if not closed.empty:
    st.subheader("Monthly Option Income")
    monthly = (
        closed.set_index(pd.to_datetime(closed["Closed"]))
        .resample("ME")["P/L"]
        .sum()
    )
    monthly_df = monthly.reset_index()
    monthly_fig = go.Figure(
        data=[
            go.Bar(
                x=monthly_df["Closed"],
                y=monthly_df["P/L"],
                marker_color=["#c48e64" if value >= 0 else "#c84d4d" for value in monthly_df["P/L"]],
                name="Realised P/L",
            )
        ]
    )
    monthly_fig.update_layout(
        height=380,
        paper_bgcolor="rgba(255,253,249,0)",
        plot_bgcolor="rgba(255,253,249,0)",
        margin=dict(t=30, r=20, b=30, l=20),
        xaxis_title="Month Closed",
        yaxis_title="Realised P/L",
    )
    st.plotly_chart(monthly_fig, width="stretch")

    st.subheader("Cumulative Option Income")
    cumulative_df = monthly.cumsum().reset_index()
    cumulative_fig = go.Figure(
        data=[
            go.Scatter(
                x=cumulative_df["Closed"],
                y=cumulative_df["P/L"],
                mode="lines",
                name="Cumulative Realised P/L",
                line=dict(color="#8f6a4f", width=3),
            )
        ]
    )
    cumulative_fig.update_layout(
        height=380,
        paper_bgcolor="rgba(255,253,249,0)",
        plot_bgcolor="rgba(255,253,249,0)",
        margin=dict(t=30, r=20, b=30, l=20),
        xaxis_title="Month Closed",
        yaxis_title="Cumulative Realised P/L",
    )
    st.plotly_chart(cumulative_fig, width="stretch")

    st.subheader("By Underlying")
    by_underlying = (
        closed.groupby(["Underlying", "Strategy"], as_index=False)
        .agg(Trades=("Contract", "count"), Premium=("Opening Value", "sum"), Fees=("Fees", "sum"), PL=("P/L", "sum"))
        .rename(columns={"PL": "Realised P/L"})
        .sort_values("Realised P/L", ascending=False)
    )
    render_data_table(by_underlying, hide_index=True)

    st.subheader("Closed Trades")
    closed_view = pd.DataFrame({
        "Contract": closed["Contract"],
        "Strategy": closed["Strategy"],
        "Contracts": closed["Contracts"],
        "Opened": closed["Opened"].dt.normalize(),
        "Closed": pd.to_datetime(closed["Closed"]).dt.normalize(),
        "Days Held": (pd.to_datetime(closed["Closed"]) - closed["Opened"]).dt.days,
        "Opening Value": closed["Opening Value"],
        "Closing Value": closed["Closing Value"],
        "Fees": closed["Fees"],
        "P/L": closed["P/L"],
        "Outcome": closed["Outcome"],
        "Return on Collateral %": closed["Return on Collateral %"],
    }).sort_values("Closed", ascending=False)
    render_data_table(closed_view, hide_index=True)
