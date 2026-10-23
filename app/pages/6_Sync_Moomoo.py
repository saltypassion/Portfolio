"""Sync page that pulls trades and dividends straight from moomoo through OpenD."""

from datetime import datetime

import streamlit as st
from src.config import DEMO_MODE
from src.importers.moomoo import (
    MoomooApiError,
    OpenDNotRunning,
    load_sync_state,
    opend_is_running,
    sync_account,
    sync_in_progress,
)
from src.io import ensure_data_files, load_source_transactions, replace_source_transactions
from src.ui import apply_app_chrome, render_data_table, render_page_header

apply_app_chrome("Sync Moomoo")
render_page_header(
    "Sync Moomoo",
    "Pull your full trade and dividend history straight from your moomoo account.",
    kicker="Data Ops",
)

ensure_data_files()

summary = st.session_state.pop("sync_summary", None)
if summary:
    st.success(summary)

trade_df = load_source_transactions("Trades")
dividend_df = load_source_transactions("Dividends")
state = load_sync_state()

last_synced = state.get("last_synced_at")
last_synced_label = (
    datetime.fromisoformat(last_synced).strftime("%d %b %Y, %H:%M") if last_synced else "Never"
)

c1, c2, c3 = st.columns(3)
c1.metric("Trades", len(trade_df))
c2.metric("Dividends", len(dividend_df))
c3.metric("Last Synced", last_synced_label)

st.caption(
    "Each sync replaces your trades and dividends with what moomoo reports, so there is nothing to import "
    "or enter by hand. Dividends include the exact withholding tax and ADR fees moomoo charged. "
    "Shares you hold without buying them (spin-offs, gifts, transfers in) are added at moomoo's average cost. "
    "Option trades are synced to the Options page. Read-only: the sync never places orders."
)

opend_up = opend_is_running()
if DEMO_MODE:
    st.warning(
        "Syncing is off in demo mode so the sample data isn't overwritten. To sync your own moomoo "
        "account, create a `data/` folder in the project, then restart the app."
    )
elif not opend_up:
    st.warning("moomoo OpenD isn't running. Open OpenD and log in, then refresh this page to sync.")
elif not state.get("cashflows_fetched_through"):
    st.info(
        "The first sync reads every day of your account history for dividends, which takes about "
        "25 minutes because of moomoo's request limits. Later syncs only read new days and take seconds."
    )



@st.fragment(run_every=2)
def show_running_sync() -> None:
    """Follow a sync started in another tab (or from the command line) until it finishes."""
    running = sync_in_progress()
    if running is None:
        st.rerun()
    started = datetime.fromisoformat(running["started_at"]).strftime("%H:%M")
    st.info(f"OpenD is syncing your account (started {started}). This page updates when it's done.")
    st.progress(min(running.get("fraction", 0.0), 1.0), text=running.get("text", "Syncing..."))


running_sync = sync_in_progress()
if running_sync:
    show_running_sync()

if st.button("Sync now", type="primary", disabled=DEMO_MODE or not opend_up or running_sync is not None):
    progress_bar = st.progress(0.0, text="Starting sync...")

    try:
        result = sync_account(progress=lambda fraction, text: progress_bar.progress(min(fraction, 1.0), text=text))
    except (OpenDNotRunning, MoomooApiError) as error:
        progress_bar.empty()
        st.error(str(error))
    else:
        progress_bar.progress(0.97, text="Saving trades, options and dividends...")
        replace_source_transactions(result.trades, result.dividends, result.options)
        progress_bar.progress(1.0, text="Sync complete")
        message = (
            f"Synced {len(result.trades)} trades ({len(result.trades) - len(trade_df):+d}) and "
            f"{len(result.dividends)} dividends ({len(result.dividends) - len(dividend_df):+d})."
        )
        if not result.options.empty:
            message += f" Synced {len(result.options)} option trades."
        if result.received_shares:
            message += " Added shares not bought through a trade: " + ", ".join(result.received_shares) + "."
        if result.position_mismatches:
            message += (
                " moomoo holds fewer shares than your trades add up to for: "
                + ", ".join(result.position_mismatches) + "."
            )
        st.session_state["sync_summary"] = message
        st.rerun()

st.subheader("Latest Trades")
if trade_df.empty:
    st.caption("No trades synced yet.")
else:
    render_data_table(trade_df.sort_values("Date", ascending=False).head(5), hide_index=True)

st.subheader("Latest Dividends")
if dividend_df.empty:
    st.caption("No dividends synced yet.")
else:
    recent_dividends = dividend_df.sort_values("Date", ascending=False).head(5).copy()
    recent_dividends["Net Cash"] = recent_dividends["Units"] * recent_dividends["Price"] - recent_dividends["Fee"]
    render_data_table(
        recent_dividends[["Date", "Ticker", "Units", "Price", "Fee", "Currency", "Net Cash"]],
        hide_index=True,
    )
