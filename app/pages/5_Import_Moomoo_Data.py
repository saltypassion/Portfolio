"""Broker-import page for previewing and appending new Moomoo trade exports."""

import streamlit as st
import pandas as pd
from pathlib import Path
from src.importers.moomoo import transform_moomoo_to_app_schema
from src.io import (
    ensure_data_files,
    import_moomoo_transactions,
    load_source_transactions,
    load_transactions,
    save_uploaded_raw_file,
)
from src.ui import apply_app_chrome, render_data_table, render_page_header

apply_app_chrome("Import Moomoo Data")
render_page_header(
    "Import Moomoo Data",
    "Upload your latest broker export, preview the cleaned trades, and merge only genuinely new entries.",
    kicker="Data Ops",
)

ensure_data_files()
trade_df = load_source_transactions("Trades")
dividend_df = load_source_transactions("Dividends")
all_df = load_transactions()

st.caption(
    "Upload your Moomoo export here. You can re-import a fresh export every month; "
    "existing trades are deduplicated before the combined transactions file is rebuilt."
)

c1, c2, c3 = st.columns(3)
c1.metric("Imported Trades", len(trade_df))
c2.metric("Manual Dividends", len(dividend_df))
c3.metric("Combined Transactions", len(all_df))

uploaded_file = st.file_uploader("Upload a CSV file", type=["csv"])

if uploaded_file is not None:
    raw_df = pd.read_csv(uploaded_file)
    st.subheader("Raw uploaded CSV")
    render_data_table(raw_df, hide_index=True)

    new_name = st.text_input(
        "File name (without .csv)",
        value=Path(uploaded_file.name).stem
    )

    try:
        st.subheader("Cleaned CSV for app")
        cleaned_df = transform_moomoo_to_app_schema(raw_df)
        render_data_table(cleaned_df, hide_index=True)

        if st.button("Save import"):
            safe_name = new_name.strip()
            if not safe_name:
                st.error("Please enter a valid file name.")
            else:
                # Save the raw broker file for audit/history, then import the cleaned rows.
                raw_path = save_uploaded_raw_file(raw_df, safe_name)
                _, net_new_df, existing_count = import_moomoo_transactions(raw_df)
                st.success(f"Raw file saved to {raw_path}")
                st.info(f"Existing imported trade rows: {existing_count}")
                st.info(f"Rows in this file: {len(cleaned_df)}")
                st.info(f"New unique trade rows added: {len(net_new_df)}")
                st.success("Trades and combined transactions have been updated.")

    except Exception as e:
        st.error(f"Failed to process CSV: {e}")
