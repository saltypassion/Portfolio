"""Manual dividend-entry page for payments missing from the broker export."""

import streamlit as st
from datetime import datetime
from src.io import append_dividend_transaction, ensure_data_files, load_source_transactions
from src.ui import apply_app_chrome, render_data_table, render_page_header

apply_app_chrome("Add Dividends")
render_page_header(
    "Add Dividends",
    "Log dividend payments that are missing from your broker export and merge them into portfolio history.",
    kicker="Data Ops",
)

ensure_data_files()

success_message = st.session_state.pop("dividend_success_message", None)
if success_message:
    st.success(success_message)

dividend_df = load_source_transactions("Dividends")


def number_input_with_blank(label: str, key: str, format_str: str) -> float | None:
    """Allow blank numeric fields while keeping simple validation close to the form."""
    raw_value = st.text_input(label, value="", key=key, placeholder="Enter value")
    if raw_value.strip() == "":
        return None

    try:
        decimals = 2 if format_str == "%.2f" else 0
        return round(float(raw_value), decimals)
    except ValueError:
        st.error(f"{label} must be a valid number.")
        return None

st.caption(
    "Use this page for dividend payments that are not present in your Moomoo export. "
    "Each saved dividend is appended to the dividend source file and merged into your full transaction history."
)

c1, c2 = st.columns(2)
c1.metric("Saved Dividends", len(dividend_df))
c2.metric(
    "Dividend Cash Received",
    f"${(dividend_df['Units'] * dividend_df['Price'] - dividend_df['Fee']).sum():,.2f}"
    if not dividend_df.empty else "$0.00"
)

st.subheader("Last 3 Dividend Entries")
if dividend_df.empty:
    st.caption("No dividends added yet.")
else:
    recent_dividends = (
        dividend_df
        .sort_values("Date", ascending=False)
        .head(3)
        .copy()
    )
    recent_dividends["Net Cash"] = (
        recent_dividends["Units"] * recent_dividends["Price"] - recent_dividends["Fee"]
    )
    render_data_table(
        recent_dividends[["Date", "Ticker", "Units", "Price", "Fee", "Currency", "Net Cash"]],
        hide_index=True,
    )

with st.form("add_transaction"):
    date = st.date_input("Date", datetime.today())
    ticker = st.text_input("Ticker").upper()
    units = number_input_with_blank("Shares held on payment date", "dividend_units", "%.2f")
    price = number_input_with_blank("Dividend per share", "dividend_price", "%.2f")
    fee = number_input_with_blank("Tax / fee withheld", "dividend_fee", "%.2f")
    currency = st.selectbox("Currency", ["USD", "SGD"])

    submitted = st.form_submit_button("Add dividend")

    if submitted:
        fee = 0.0 if fee is None else fee

        if not ticker.strip():
            st.error("Ticker is required.")
        elif units is None or price is None:
            st.error("Shares and dividend per share are required.")
        elif units <= 0 or price <= 0:
            st.error("Shares and dividend per share must be greater than 0.")
        else:
            append_dividend_transaction(
                date=date,
                ticker=ticker.strip().upper(),
                shares=units,
                dividend_per_share=price,
                fee=fee,
                currency=currency,
            )
            received = units * price - fee
            st.session_state["dividend_success_message"] = (
                f"Dividend added. Net cash recorded: ${received:,.2f}"
            )
            st.rerun()
