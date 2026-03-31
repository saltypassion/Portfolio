"""Buy/sell watchlist page with add, edit, remove, and stock-detail jump actions."""

import math
from datetime import datetime

import streamlit as st

from src.io import (
    append_watchlist_item,
    delete_watchlist_item,
    load_watchlist,
    update_watchlist_item,
)
from src.pricing import get_latest_prices, get_ticker_profiles
from src.ui import apply_app_chrome, parse_optional_float, render_data_table, render_page_header


def build_watchlist_view(watchlist_df):
    """Enrich raw watchlist rows with live prices, profiles, and derived status."""
    if watchlist_df.empty:
        return watchlist_df.copy()

    prices = get_latest_prices(watchlist_df["Ticker"].tolist())
    profiles = get_ticker_profiles(tuple(watchlist_df["Ticker"].tolist()))
    view = watchlist_df.merge(profiles, on="Ticker", how="left")
    view["Current Price"] = view["Ticker"].map(prices).fillna(0.0)
    view["Gap to Target"] = view["Current Price"] - view["Target Price"]
    view["Status"] = view.apply(compute_status, axis=1)
    return view


def compute_status(row):
    """Compute readiness based on watch type and current price vs target."""
    if row["Current Price"] <= 0:
        return "No Price"
    if row["Watch Type"] == "Sell":
        return "Ready" if row["Current Price"] >= row["Target Price"] else "Watching"
    return "Ready" if row["Current Price"] <= row["Target Price"] else "Watching"


def optional_float_to_text(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return f"{float(value):.2f}"


def blank_number_input(label: str, key: str, placeholder: str = "Enter value") -> float | None:
    raw_value = st.text_input(label, value="", placeholder=placeholder, key=key)
    try:
        return parse_optional_float(raw_value, decimals=2)
    except ValueError:
        st.error(f"{label} must be a valid number.")
        return None


def render_watchlist_tab(tab_label: str, watch_type: str, full_watchlist_df):
    """Render one buy/sell tab so the two workflows stay structurally consistent."""
    scoped_df = full_watchlist_df[full_watchlist_df["Watch Type"] == watch_type].copy()
    scoped_view = build_watchlist_view(scoped_df)
    singular_label = f"{watch_type} Watchlist"

    c1, c2 = st.columns(2)
    c1.metric(f"{tab_label} Items", str(len(scoped_df)))
    c2.metric(
        "Ready",
        str(int((scoped_view["Status"] == "Ready").sum())) if not scoped_view.empty else "0",
    )

    st.subheader(f"{tab_label} Table")
    if scoped_view.empty:
        st.info(f"No {watch_type.lower()} watchlist entries yet.")
    else:
        render_data_table(
            scoped_view[
                [
                    "Ticker",
                    "Name",
                    "Type",
                    "Sector",
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

        open_options = sorted(scoped_view["Ticker"].dropna().unique().tolist())
        selected_open_ticker = st.selectbox(
            "Open stock details",
            open_options,
            key=f"open_stock_details_{watch_type}",
        )
        if st.button(
            f"Open {selected_open_ticker} in Stock Details",
            key=f"go_stock_details_{watch_type}",
            type="primary",
        ):
            st.session_state["selected_ticker"] = selected_open_ticker
            st.switch_page("pages/1_Stock_Details.py")

    target_label = "Target Buy Price" if watch_type == "Buy" else "Target Sell Price"
    st.subheader(f"Add {singular_label} Item")
    with st.form(f"add_watchlist_item_{watch_type.lower()}"):
        date_added = st.date_input("Date Added", datetime.today(), key=f"add_date_{watch_type}")
        ticker = st.text_input("Ticker", key=f"add_ticker_{watch_type}").upper()
        target_price = blank_number_input(target_label, key=f"add_target_{watch_type}")
        fair_value_input = st.text_input(
            "Fair / Intrinsic Value",
            value="",
            placeholder="Optional",
            key=f"add_fair_{watch_type}",
        )
        priority = st.selectbox("Priority", ["High", "Medium", "Low"], key=f"add_priority_{watch_type}")
        notes = st.text_area("Notes", placeholder="Why are you watching this stock?", key=f"add_notes_{watch_type}")
        submitted = st.form_submit_button(f"Add to {tab_label.lower()}")

        if submitted:
            if not ticker.strip():
                st.error("Ticker is required.")
            elif target_price is None:
                st.error("Target price is required.")
            elif target_price <= 0:
                st.error("Target price must be greater than 0.")
            else:
                try:
                    fair_value = parse_optional_float(fair_value_input, decimals=2)
                except ValueError:
                    st.error("Fair / Intrinsic Value must be a number.")
                else:
                    append_watchlist_item(
                        date_added=date_added,
                        ticker=ticker.strip().upper(),
                        watch_type=watch_type,
                        target_price=target_price,
                        fair_value=fair_value,
                        priority=priority,
                        notes=notes,
                    )
                    st.session_state["watchlist_success_message"] = (
                        f"{ticker.strip().upper()} added to {tab_label.lower()}."
                    )
                    st.rerun()

    st.subheader(f"Edit {singular_label} Item")
    if scoped_df.empty:
        st.caption("Nothing to edit yet.")
    else:
        edit_options = [
            f"{row['Ticker']} | {row['Date Added'].strftime('%Y-%m-%d')} | {row['Target Price']:.2f}"
            for _, row in scoped_df.iterrows()
        ]
        selected_edit_item = st.selectbox(
            "Select watchlist item to edit",
            edit_options,
            key=f"edit_select_{watch_type}",
        )
        edit_ticker, edit_date, _ = selected_edit_item.split(" | ", 2)
        current_row = scoped_df[
            (scoped_df["Ticker"] == edit_ticker) &
            (scoped_df["Date Added"].dt.strftime("%Y-%m-%d") == edit_date)
        ].iloc[0]
        edit_key_suffix = f"{watch_type}_{edit_ticker}_{edit_date}".replace("-", "_")

        with st.form(f"edit_watchlist_item_{watch_type.lower()}"):
            edited_target_price = st.number_input(
                f"Edit {target_label}",
                min_value=0.0,
                value=float(current_row["Target Price"]),
                format="%.2f",
                key=f"edit_target_{edit_key_suffix}",
            )
            edited_fair_value_input = st.text_input(
                "Edit Fair / Intrinsic Value",
                value=optional_float_to_text(current_row["Fair Value"]),
                placeholder="Optional",
                key=f"edit_fair_{edit_key_suffix}",
            )
            edited_priority = st.selectbox(
                "Edit Priority",
                ["High", "Medium", "Low"],
                index=["High", "Medium", "Low"].index(current_row["Priority"]),
                key=f"edit_priority_{edit_key_suffix}",
            )
            edited_notes = st.text_area(
                "Edit Notes",
                value=current_row["Notes"],
                key=f"edit_notes_{edit_key_suffix}",
            )
            edit_submitted = st.form_submit_button("Save watchlist changes")

            if edit_submitted:
                if edited_target_price <= 0:
                    st.error("Target price must be greater than 0.")
                else:
                    try:
                        edited_fair_value = parse_optional_float(edited_fair_value_input, decimals=2)
                    except ValueError:
                        st.error("Fair / Intrinsic Value must be a number.")
                    else:
                        updated = update_watchlist_item(
                            original_ticker=edit_ticker,
                            original_date_added=edit_date,
                            watch_type=watch_type,
                            target_price=edited_target_price,
                            fair_value=edited_fair_value,
                            priority=edited_priority,
                            notes=edited_notes,
                        )
                        if updated:
                            st.session_state["watchlist_success_message"] = (
                                f"{edit_ticker} watchlist item updated."
                            )
                            st.rerun()
                        else:
                            st.error("Unable to update that watchlist item.")

    st.subheader(f"Remove {singular_label} Item")
    if scoped_df.empty:
        st.caption("Nothing to remove yet.")
    else:
        removal_options = [
            f"{row['Ticker']} | {row['Date Added'].strftime('%Y-%m-%d')} | {row['Target Price']:.2f}"
            for _, row in scoped_df.iterrows()
        ]
        selected_item = st.selectbox(
            "Select watchlist item to remove",
            removal_options,
            key=f"remove_select_{watch_type}",
        )

        if st.button("Remove selected item", type="primary", key=f"watchlist_remove_{watch_type}"):
            ticker_value, date_value, _ = selected_item.split(" | ", 2)
            deleted = delete_watchlist_item(ticker_value, date_value)
            if deleted:
                st.success("Watchlist item removed.")
                st.rerun()
            else:
                st.error("Unable to remove that watchlist item.")


apply_app_chrome("Watchlist")
render_page_header(
    "Watchlist",
    "Track stocks you want to buy or sell, set target prices, and see when they are ready.",
    kicker="Ideas",
)

success_message = st.session_state.pop("watchlist_success_message", None)
if success_message:
    st.success(success_message)

watchlist_df = load_watchlist()

buy_tab, sell_tab = st.tabs(["Buy Watchlist", "Sell Watchlist"])

with buy_tab:
    render_watchlist_tab("Buy Watchlist", "Buy", watchlist_df)

with sell_tab:
    render_watchlist_tab("Sell Watchlist", "Sell", watchlist_df)
