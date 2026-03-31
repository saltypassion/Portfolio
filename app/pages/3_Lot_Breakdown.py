"""Open-lot page for inspecting remaining FIFO lots by ticker and age."""

import streamlit as st
import sys
import os
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from src.io import load_transactions
from src.fifo import run_fifo
from src.metrics import lot_breakdown
from src.pricing import get_latest_prices
from src.ui import apply_app_chrome, format_compact_quantity, render_data_table, render_page_header

apply_app_chrome("Lot Breakdown")
render_page_header(
    "Lot Breakdown",
    "See the remaining buy lots that make up your open positions and current cost basis.",
    kicker="Positions",
)

# ---------- LOAD DATA ----------
df = load_transactions()

# FIFO output is reused here because lot detail depends on the remaining buy lots.
portfolio, realised, dividends = run_fifo(df)

# ---------- DISPLAY LOTS ----------
lot_df = lot_breakdown(portfolio)

if lot_df.empty:
    st.info("No open buy lots right now.")
    st.stop()

lot_df = lot_df.copy()
lot_df["Buy Date"] = pd.to_datetime(lot_df["Buy Date"])
lot_df["Days Held"] = (pd.Timestamp.today().normalize() - lot_df["Buy Date"].dt.normalize()).dt.days
lot_df["Months Held"] = (lot_df["Days Held"] / 30.44).round(1)

latest_prices = get_latest_prices(lot_df["Ticker"].unique().tolist())
# Lot-level unrealised numbers depend on live prices, not transaction prices.
lot_df["Current Price"] = lot_df["Ticker"].map(latest_prices).fillna(0.0)
lot_df["Current Value"] = lot_df["Remaining Shares"] * lot_df["Current Price"]
lot_df["Unrealised P/L"] = lot_df["Current Value"] - lot_df["Total Cost"]
lot_df["Unrealised %"] = (
    lot_df["Unrealised P/L"] / lot_df["Total Cost"] * 100
).round(2)

total_open_lots = len(lot_df)
total_shares = lot_df["Remaining Shares"].sum()
total_cost_basis = lot_df["Total Cost"].sum()
total_value = lot_df["Current Value"].sum()

m1, m2, m3, m4 = st.columns(4)
m1.metric("Open Lots", str(total_open_lots))
m2.metric("Total Shares", format_compact_quantity(total_shares))
m3.metric("Cost Basis", f"${total_cost_basis:,.2f}")
m4.metric("Current Value", f"${total_value:,.2f}")

st.subheader("Ticker Summary")
ticker_summary = (
    lot_df.groupby("Ticker", as_index=False)
    .agg(
        Lots=("Ticker", "size"),
        Shares=("Remaining Shares", "sum"),
        Cost_Basis=("Total Cost", "sum"),
        Current_Value=("Current Value", "sum"),
        Oldest_Lot=("Buy Date", "min"),
        Average_Days_Held=("Days Held", "mean"),
    )
)
ticker_summary["Current Price"] = ticker_summary["Ticker"].map(latest_prices).fillna(0.0)
ticker_summary["Unrealised P/L"] = ticker_summary["Current_Value"] - ticker_summary["Cost_Basis"]
ticker_summary["Unrealised %"] = (
    ticker_summary["Unrealised P/L"] / ticker_summary["Cost_Basis"] * 100
).round(2)
ticker_summary["Average Days Held"] = ticker_summary["Average_Days_Held"].round(0).astype(int)
ticker_summary = ticker_summary.rename(
    columns={
        "Cost_Basis": "Cost Basis",
        "Current_Value": "Current Value",
        "Oldest_Lot": "Oldest Lot",
    }
).sort_values("Current Value", ascending=False)
render_data_table(
    ticker_summary[
        [
            "Ticker",
            "Lots",
            "Shares",
            "Current Price",
            "Cost Basis",
            "Current Value",
            "Unrealised P/L",
            "Unrealised %",
            "Oldest Lot",
            "Average Days Held",
        ]
    ],
    hide_index=True,
)

st.subheader("Lot Detail by Ticker")
for ticker in ticker_summary["Ticker"]:
    ticker_lots = lot_df[lot_df["Ticker"] == ticker].copy().sort_values("Buy Date")
    ticker_cost = ticker_lots["Total Cost"].sum()
    ticker_value = ticker_lots["Current Value"].sum()
    ticker_pl = ticker_value - ticker_cost
    ticker_pl_pct = (ticker_pl / ticker_cost * 100) if ticker_cost else 0

    with st.expander(
        f"{ticker} | {len(ticker_lots)} lots | ${ticker_value:,.2f} value | {ticker_pl_pct:.2f}% unrealised",
        expanded=False,
    ):
        info1, info2, info3, info4 = st.columns(4)
        info1.metric("Shares", format_compact_quantity(ticker_lots["Remaining Shares"].sum()))
        info2.metric("Cost Basis", f"${ticker_cost:,.2f}")
        info3.metric("Current Value", f"${ticker_value:,.2f}")
        info4.metric("Unrealised P/L", f"${ticker_pl:,.2f}", f"{ticker_pl_pct:.2f}%")

        render_data_table(
            ticker_lots[
                [
                    "Buy Date",
                    "Remaining Shares",
                    "Cost Per Share",
                    "Current Price",
                    "Total Cost",
                    "Current Value",
                    "Unrealised P/L",
                    "Unrealised %",
                    "Days Held",
                    "Months Held",
                ]
            ],
            hide_index=True,
        )
