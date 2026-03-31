"""Single-ticker analysis page for both held positions and watchlist names."""

import streamlit as st
import plotly.graph_objects as go

from src.io import load_transactions, load_watchlist
from src.pricing import get_price_history, get_ticker_profiles
from src.metrics import build_average_cost_curve
from src.ui import apply_app_chrome, format_compact_quantity, render_data_table, render_page_header

apply_app_chrome("Stock Details")

# -------------------------
# Load transactions
# -------------------------

df = load_transactions()
watchlist_df = load_watchlist()
tickers = sorted(set(df["Ticker"].unique()).union(set(watchlist_df["Ticker"].unique())))

if not tickers:
    st.info("No portfolio or watchlist tickers available yet.")
    st.stop()

ticker = st.session_state.get("selected_ticker", tickers[0])

ticker = st.selectbox(
    "Select Stock",
    tickers,
    index=tickers.index(ticker),
    key="stock_detail_ticker"
)

render_page_header(
    f"{ticker} Stock Details",
    "Inspect price action, average cost, realised gains, and dividend receipts for a single holding.",
    kicker="Analysis",
)

# -------------------------
# Filter transactions
# -------------------------

stock_tx = df[df["Ticker"] == ticker]
stock_watchlist = (
    watchlist_df[watchlist_df["Ticker"] == ticker]
    .sort_values(["Watch Type", "Date Added"], ascending=[True, False])
    .copy()
)
profile_df = get_ticker_profiles((ticker,))
profile = profile_df.iloc[0].to_dict() if not profile_df.empty else {
    "Name": ticker,
    "Type": "",
    "Sector": "",
    "Industry": "",
    "Fund Category": "",
    "Fund Family": "",
}

is_fund = profile.get("Type", "") in {"ETF", "MUTUALFUND"}
# Reuse the same three profile cards while swapping ETF-specific labels when needed.
middle_label = "Fund Category" if is_fund else "Sector"
right_label = "Fund Family" if is_fund else "Industry"
middle_value = (
    profile.get("Fund Category", "")
    if is_fund
    else profile.get("Sector", "")
)
right_value = (
    profile.get("Fund Family", "")
    if is_fund
    else profile.get("Industry", "")
)

st.markdown(
    f"""
    <div class="info-card">
        <div class="info-label">Name</div>
        <div class="info-value">{profile.get("Name", ticker)}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

meta1, meta2, meta3 = st.columns(3)
meta1.markdown(
    f"""
    <div class="info-card info-card--compact">
        <div class="info-label">Type</div>
        <div class="info-value">{profile.get("Type", "") or "-"}</div>
    </div>
    """,
    unsafe_allow_html=True,
)
meta2.markdown(
    f"""
    <div class="info-card info-card--compact">
        <div class="info-label">{middle_label}</div>
        <div class="info-value">{middle_value or "-"}</div>
    </div>
    """,
    unsafe_allow_html=True,
)
meta3.markdown(
    f"""
    <div class="info-card info-card--compact">
        <div class="info-label">{right_label}</div>
        <div class="info-value">{right_value or "-"}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# -------------------------
# Position calculations
# -------------------------

buys = stock_tx[stock_tx["Type"] == "Buy"]
sells = stock_tx[stock_tx["Type"] == "Sell"]

shares = buys["Units"].sum() - sells["Units"].sum()
total_units_bought = buys["Units"].sum()
avg_cost = (buys["Units"] * buys["Price"]).sum() / total_units_bought if total_units_bought > 0 else 0.0

# -------------------------
# Realised profit
# -------------------------

total_buy_cost = (buys["Units"] * buys["Price"]).sum()
total_sell_value = (sells["Units"] * sells["Price"]).sum()
avg_buy_price = total_buy_cost / total_units_bought if total_units_bought > 0 else 0
realised_profit = total_sell_value - (sells["Units"].sum() * avg_buy_price)

# -------------------------
# Price data
# -------------------------
default_period = st.session_state.get("stock_detail_period", "1y")
period_options = ["1mo", "3mo", "6mo", "1y", "3y", "5y", "max"]
period = default_period if default_period in period_options else "1y"
price_data = get_price_history(ticker, period)
price_data.index = price_data.index.tz_localize(None)
price = price_data["Close"].iloc[-1]

value = shares * price
cost_basis = shares * avg_cost
pl = value - cost_basis
return_pct = pl / cost_basis * 100 if cost_basis != 0 else 0

if not stock_watchlist.empty:
    watchlist_view = stock_watchlist.copy()
    watchlist_view["Current Price"] = price
    # Keep watchlist status logic in sync with the dedicated watchlist page.
    watchlist_view["Status"] = watchlist_view.apply(
        lambda row: (
            "No Price"
            if row["Current Price"] <= 0
            else "Ready"
            if (
                row["Watch Type"] == "Sell" and row["Current Price"] >= row["Target Price"]
            ) or (
                row["Watch Type"] != "Sell" and row["Current Price"] <= row["Target Price"]
            )
            else "Watching"
        ),
        axis=1,
    )

    st.subheader("Watchlist Details")
    render_data_table(
        watchlist_view[
            [
                "Date Added",
                "Watch Type",
                "Target Price",
                "Current Price",
                "Fair Value",
                "Priority",
                "Status",
                "Notes",
            ]
        ],
        hide_index=True,
    )

st.divider()

# -------------------------
# Portfolio metrics
# -------------------------

col1, col2, col3, col4 = st.columns(4)
col1.metric("Shares", format_compact_quantity(shares))
col2.metric("Average Cost", f"${avg_cost:.2f}")
col3.metric("Current Price", f"${price:.2f}")
col4.metric("Position Value", f"${value:,.2f}")

col1, col2, col3 = st.columns(3)
col1.metric("Cost Basis", f"${cost_basis:,.2f}")
col2.metric("Unrealised P/L", f"${pl:,.2f}", f"{return_pct:.2f}%")
col3.metric("Realised P/L", f"${realised_profit:,.2f}")

# -------------------------
# Price vs Average Cost
# -------------------------

st.subheader("Price vs Your Average Cost")
period = st.selectbox(
    "Select time range",
    period_options,
    index=period_options.index(period),
    key="stock_detail_period",
)
price_data = get_price_history(ticker, period)
price_data.index = price_data.index.tz_localize(None)
price = price_data["Close"].iloc[-1]

fig = go.Figure()

# Stock price (main line)
fig.add_trace(
    go.Scatter(
        x=price_data.index,
        y=price_data["Close"],
        name="Stock Price",
        line=dict(width=3)
    )
)

avg_curve = build_average_cost_curve(df, ticker)
if not avg_curve.empty and avg_curve["Average Cost"].notna().any():
    current_avg_cost = avg_curve["Average Cost"].dropna().iloc[-1]
    fig.add_trace(
        go.Scatter(
            x=price_data.index,
            y=[current_avg_cost] * len(price_data.index),
            name="Average Cost",
            line=dict(
                width=3,
                dash="dash",
                color="rgba(120, 108, 95, 0.95)"
            ),
        )
    )

fig.update_layout(
    height=500,
    xaxis_title="Date",
    yaxis_title="Price",
    paper_bgcolor="rgba(255,253,249,0)",
    plot_bgcolor="rgba(255,253,249,0)",
    margin=dict(t=90, r=40, b=40, l=40),
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.08,
        xanchor="left",
        x=0,
        font=dict(size=13),
    ),
)

chart_start = price_data.index.min()
buys = stock_tx[
    (stock_tx["Type"] == "Buy") &
    (stock_tx["Date"] >= chart_start)
]

# buy markers
fig.add_trace(
    go.Scatter(
        x=buys["Date"],
        y=buys["Price"],
        mode="markers",
        name="Buy",
        marker=dict(
            symbol="triangle-up",
            size=12,
            color="green"
        )
    )
)

sells = stock_tx[
    (stock_tx["Type"] == "Sell") &
    (stock_tx["Date"] >= chart_start)
]
# sell markers
fig.add_trace(
    go.Scatter(
        x=sells["Date"],
        y=sells["Price"],
        mode="markers",
        name="Sell",
        marker=dict(
            symbol="triangle-down",
            size=12,
            color="red"
        )
    )
)

st.plotly_chart(fig, use_container_width=True)

# -------------------------
# Transactions
# -------------------------

st.subheader("Your Transactions")
table_df = (
    stock_tx
    .sort_values("Date", ascending=True)
    .dropna(how="all")
    .reset_index(drop=True)
)
if table_df.empty:
    st.caption("No transactions recorded for this ticker yet.")
else:
    render_data_table(
        table_df,
        hide_index=True,
    )

# -------------------------
# Dividend data
# -------------------------

st.subheader("Dividends")

dividend_tx = stock_tx[stock_tx["Type"] == "Dividend"].copy()

if not dividend_tx.empty:

    # calculate actual dividend cash received
    dividend_tx["Dividend Amount"] = dividend_tx["Units"] * dividend_tx["Price"] - dividend_tx["Fee"]

    total_dividends = dividend_tx["Dividend Amount"].sum()

    st.metric("Total Dividends Received", f"${total_dividends:,.2f}")

    # dividend chart
    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            x=dividend_tx["Date"],
            y=dividend_tx["Dividend Amount"],
            name="Dividend",
            marker_color="green"
        )
    )

    fig.update_layout(
        title="Dividend Payments",
        xaxis_title="Date",
        yaxis_title="Dividend Received",
        height=400,
        paper_bgcolor="rgba(255,253,249,0)",
        plot_bgcolor="rgba(255,253,249,0)",
        margin=dict(t=60, r=30, b=40, l=30),
    )

    st.plotly_chart(fig, use_container_width=True)

else:
    st.write("No dividend transactions recorded for this stock.")
