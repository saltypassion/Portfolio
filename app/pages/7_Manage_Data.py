"""Administrative page for removing the most recently imported trade/dividend row."""

import streamlit as st
from src.io import delete_last_transaction, load_source_transactions
from src.ui import apply_app_chrome, render_data_table, render_page_header

apply_app_chrome("Manage Data")
render_page_header(
    "Manage Data",
    "Review the latest imported rows and remove the last trade or dividend entry when you need to correct a bad import.",
    kicker="Maintenance",
)
st.markdown(
    """
    <style>
    /* Keep destructive actions visually distinct from the default warm buttons. */
    .st-key-delete_last_entry button {
        background: linear-gradient(135deg, #c84d4d 0%, #de6b6b 100%);
        box-shadow: 0 12px 20px rgba(200, 77, 77, 0.22);
        color: white;
    }

    .st-key-delete_last_entry button:hover {
        background: linear-gradient(135deg, #b33f3f 0%, #cd5757 100%);
    }

    .st-key-delete_last_entry button:disabled {
        background: linear-gradient(135deg, #e6c4c4 0%, #edd1d1 100%);
        color: #8c5f5f;
        box-shadow: none;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

source = st.selectbox("Select source", ["Trades", "Dividends"])
df_raw = load_source_transactions(source)

if df_raw.empty:
    st.info(f"No {source.lower()} to delete.")
else:
    # Show the last 5 rows
    last_rows = df_raw.tail(5)
    st.write(f"This will delete the last row in your {source.lower()} source file:")
    render_data_table(last_rows, hide_index=True)

    col1, col2 = st.columns([1, 2])
    confirm = col1.checkbox("I understand and want to delete it")
    delete_btn = col2.button(
        f"Delete last {source[:-1].lower()}",
        type="primary",
        disabled=not confirm,
        key="delete_last_entry",
    )

    if delete_btn:
        deleted = delete_last_transaction(source)
        if deleted:
            st.success(f"Deleted last {source[:-1].lower()} and rebuilt transactions.")
            st.rerun()
        else:
            st.info("Nothing to delete.")
