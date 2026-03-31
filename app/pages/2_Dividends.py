"""Dividend-income page with stock-level totals and trend charts."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import sys
import os
from src.io import load_transactions
from src.ui import apply_app_chrome, render_data_table, render_page_header

apply_app_chrome("Dividends")
render_page_header(
    "Dividends",
    "Track total cash received, monthly income rhythm, and which holdings are doing the work.",
    kicker="Income",
)

df = load_transactions()
div_df = df[df["Type"] == "Dividend"].copy()

if div_df.empty:
    st.info("No dividends recorded yet.")
    st.stop()

# Amount already computed as TotalCost in io.py (units*price - fee)
div_df["Amount"] = div_df["TotalCost"]

total_div = div_df["Amount"].sum()
st.metric("Total Dividends Earned", f"${total_div:,.2f}")

st.subheader("Dividends by Stock")
by_stock = (
    div_df.groupby("Ticker")["Amount"]
    .sum()
    .sort_values(ascending=False)
    .reset_index()
)
render_data_table(by_stock, hide_index=True)

st.subheader("Monthly Dividends")
div_df["Date"] = pd.to_datetime(div_df["Date"])
div_df["Amount"] = div_df["Units"] * div_df["Price"] - div_df["Fee"]
monthly = (
    div_df
    .set_index("Date")
    .resample("ME")["Amount"]
    .sum()
)
monthly_df = monthly.reset_index()
monthly_fig = go.Figure(
    data=[
        go.Bar(
            x=monthly_df["Date"],
            y=monthly_df["Amount"],
            marker_color="#c48e64",
            name="Monthly Dividends",
        )
    ]
)
monthly_fig.update_layout(
    height=380,
    paper_bgcolor="rgba(255,253,249,0)",
    plot_bgcolor="rgba(255,253,249,0)",
    margin=dict(t=30, r=20, b=30, l=20),
    xaxis_title="Month",
    yaxis_title="Dividend Amount",
)
st.plotly_chart(monthly_fig, use_container_width=True)

st.subheader("Cumulative Dividends")
cumulative = monthly.cumsum()
cumulative_df = cumulative.reset_index()
cumulative_fig = go.Figure(
    data=[
        go.Scatter(
            x=cumulative_df["Date"],
            y=cumulative_df["Amount"],
            mode="lines",
            name="Cumulative Dividends",
            line=dict(color="#8f6a4f", width=3),
        )
    ]
)
cumulative_fig.update_layout(
    height=380,
    paper_bgcolor="rgba(255,253,249,0)",
    plot_bgcolor="rgba(255,253,249,0)",
    margin=dict(t=30, r=20, b=30, l=20),
    xaxis_title="Month",
    yaxis_title="Cumulative Dividends",
)
st.plotly_chart(cumulative_fig, use_container_width=True)
