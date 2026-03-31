"""Shared formatting, CSS, and rendering helpers for the Streamlit app."""

import pandas as pd
import streamlit as st


def format_compact_quantity(value, max_decimals: int = 4) -> str:
    """Display quantities without forced trailing zeros."""
    if pd.isna(value):
        return ""

    numeric = float(value)
    if numeric.is_integer():
        return f"{int(numeric):,}"

    formatted = f"{numeric:,.{max_decimals}f}".rstrip("0").rstrip(".")
    return formatted


def parse_optional_float(raw_value: str, decimals: int = 2) -> float | None:
    """Allow blank form fields while still parsing numeric text when provided."""
    if raw_value is None:
        return None

    stripped = str(raw_value).strip()
    if stripped == "":
        return None

    return round(float(stripped), decimals)


def apply_app_chrome(page_title: str) -> None:
    """Apply the shared layout, theme, and widget styling to each page."""
    st.set_page_config(page_title=page_title, layout="wide")
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700;800&display=swap');

        :root {
            color-scheme: light;
        }

        html, body, [class*="css"] {
            font-family: "Manrope", sans-serif;
            color: #3f3125;
        }

        body {
            background: #fbf6ef;
        }

        [data-testid="stAppViewContainer"] {
            background:
                radial-gradient(circle at top left, rgba(212, 176, 139, 0.14), transparent 26%),
                radial-gradient(circle at top right, rgba(193, 164, 134, 0.12), transparent 24%),
                linear-gradient(180deg, #fbf6ef 0%, #f5ecdf 48%, #efe3d3 100%);
            color: #3f3125;
        }

        [data-testid="stAppViewContainer"] *:not([data-testid="stSidebar"] *):not(.hero-card *),
        [data-testid="stMarkdownContainer"],
        [data-testid="stMarkdownContainer"] p,
        [data-testid="stMarkdownContainer"] li,
        [data-testid="stMarkdownContainer"] span,
        [data-testid="stCaptionContainer"],
        [data-testid="stCaptionContainer"] *,
        [data-testid="stMetricLabel"],
        [data-testid="stMetricValue"],
        label,
        p,
        li {
            color: #3f3125;
        }

        [data-testid="stHeader"] {
            background: rgba(251, 246, 239, 0.78);
            backdrop-filter: blur(10px);
        }

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #b68c67 0%, #9b7655 100%);
            border-right: 1px solid rgba(255, 248, 240, 0.12);
        }

        [data-testid="stSidebar"] * {
            color: #fff7ef;
        }

        [data-testid="stSidebarNav"] {
            padding-top: 1rem;
        }

        [data-testid="stSidebarNav"]::before {
            content: "Portfolio HQ";
            display: block;
            font-size: 1.15rem;
            font-weight: 800;
            letter-spacing: 0.04em;
            margin: 0 0 1rem 0.65rem;
            color: #f7ddbf;
        }

        [data-testid="stSidebarNav"] a {
            border-radius: 14px;
            margin: 0.15rem 0.45rem;
            padding: 0.35rem 0.55rem;
        }

        [data-testid="stSidebarNav"] a:hover {
            background: rgba(255, 255, 255, 0.08);
        }

        [data-testid="stSidebarNav"] a[aria-current="page"] {
            background: linear-gradient(135deg, rgba(247, 221, 191, 0.18), rgba(255, 255, 255, 0.08));
            border: 1px solid rgba(247, 221, 191, 0.32);
        }

        .block-container {
            padding-top: 4rem !important;
            padding-bottom: 2.5rem;
            max-width: 1180px;
        }

        .block-container > div:first-child {
            margin-top: 0;
        }

        .hero-card {
            background: linear-gradient(135deg, rgba(171, 131, 97, 0.95), rgba(196, 158, 122, 0.92));
            border: 1px solid rgba(247, 221, 191, 0.24);
            color: #fbf5ee;
            border-radius: 28px;
            padding: 1.7rem 1.5rem 1.25rem 1.5rem;
            margin-bottom: 1.4rem;
            box-shadow: 0 20px 40px rgba(99, 71, 50, 0.12);
        }

        .hero-kicker {
            text-transform: uppercase;
            letter-spacing: 0.16em;
            font-size: 0.72rem;
            font-weight: 700;
            color: #f7ddbf;
            margin-bottom: 0.55rem;
        }

        .hero-title {
            font-size: 2.2rem;
            line-height: 1.05;
            font-weight: 800;
            margin: 0;
        }

        .hero-subtitle {
            margin-top: 0.55rem;
            max-width: 48rem;
            color: rgba(251, 245, 238, 0.84);
            font-size: 0.98rem;
        }

        .info-card {
            display: block;
            width: 100%;
            box-sizing: border-box;
            background: rgba(255, 249, 242, 0.86);
            border: 1px solid rgba(111, 77, 53, 0.10);
            border-radius: 22px;
            padding: 1rem 1.1rem;
            box-shadow: 0 10px 24px rgba(99, 71, 50, 0.06);
            min-height: 124px;
            margin-bottom: 1rem;
        }

        .info-card--compact {
            min-height: 110px;
        }

        .info-label {
            color: #745743;
            font-size: 0.82rem;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            font-weight: 700;
            margin-bottom: 0.45rem;
        }

        .info-value {
            color: #3e3228;
            font-size: clamp(1.25rem, 2.1vw, 2rem);
            line-height: 1.15;
            font-weight: 700;
            overflow-wrap: anywhere;
        }

        .meta-strip {
            background: rgba(255, 249, 242, 0.78);
            border: 1px solid rgba(111, 77, 53, 0.10);
            border-radius: 22px;
            padding: 1rem 1.1rem;
            box-shadow: 0 10px 24px rgba(99, 71, 50, 0.05);
        }

        .meta-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 1rem;
        }

        .meta-item {
            min-width: 0;
        }

        .meta-item .info-value {
            font-size: clamp(1rem, 1.5vw, 1.3rem);
            font-weight: 600;
        }

        [data-testid="stMetric"] {
            background: rgba(255, 249, 242, 0.82);
            border: 1px solid rgba(111, 77, 53, 0.10);
            border-radius: 22px;
            padding: 0.85rem 1rem;
            box-shadow: 0 10px 24px rgba(99, 71, 50, 0.06);
        }

        [data-testid="stDataFrame"], .stPlotlyChart, [data-testid="stForm"] {
            background: rgba(255, 249, 242, 0.8);
            border: 1px solid rgba(111, 77, 53, 0.10);
            border-radius: 22px;
            padding: 0.35rem;
            box-shadow: 0 10px 24px rgba(99, 71, 50, 0.06);
            overflow: hidden;
        }

        [data-testid="stDataFrame"] > div {
            border-radius: 18px;
            overflow: hidden;
        }

        [data-testid="stDataFrame"] [role="table"] {
            border-radius: 18px;
            overflow: hidden;
        }

        [data-testid="stDataFrame"] [data-testid="stDataFrameResizable"] {
            border-radius: 18px;
            overflow: hidden;
        }

        [data-testid="stForm"] {
            background: rgba(255, 250, 244, 0.96);
            padding: 1.1rem;
        }

        .stPlotlyChart {
            background: rgba(255, 253, 249, 0.96);
            padding: 0.15rem;
            overflow: hidden;
        }

        .stPlotlyChart > div {
            border-radius: 20px;
            overflow: hidden;
        }

        /* Give all common form fields the same warm input shell. */
        [data-baseweb="input"] > div,
        [data-baseweb="base-input"] > div,
        [data-baseweb="select"] > div,
        [data-testid="stDateInput"] > div,
        [data-testid="stSelectbox"] > div,
        [data-testid="stTextInput"] > div,
        [data-testid="stTextArea"] > div,
        [data-testid="stNumberInput"] > div {
            background: #fff8ef;
            border: 1px solid rgba(122, 88, 61, 0.28);
            border-radius: 16px;
        }

        /* Remove extra background layers from Streamlit form wrappers. */
        [data-testid="stForm"] [data-baseweb="input"],
        [data-testid="stForm"] [data-baseweb="base-input"],
        [data-testid="stForm"] [data-baseweb="select"],
        [data-testid="stForm"] [data-testid="stTextInput"],
        [data-testid="stForm"] [data-testid="stTextArea"],
        [data-testid="stForm"] [data-testid="stNumberInput"],
        [data-testid="stForm"] [data-testid="stDateInput"],
        [data-testid="stForm"] [data-testid="stSelectbox"] {
            background: transparent !important;
        }

        /* Date inputs have deeper nested wrappers that need to be neutralized. */
        [data-testid="stDateInput"] > div > div,
        [data-testid="stForm"] [data-testid="stDateInput"] > div > div,
        [data-testid="stDateInput"] [data-baseweb="input"],
        [data-testid="stDateInput"] [data-baseweb="base-input"],
        [data-testid="stDateInput"] [data-baseweb="input"] > div > div,
        [data-testid="stDateInput"] [data-baseweb="base-input"] > div > div {
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
        } 

        [data-testid="stForm"] textarea {
            background: #fff8ef !important;
            border: 1px solid rgba(122, 88, 61, 0.28) !important;
            border-radius: 16px !important;
            outline: none !important;
            box-shadow: none !important;
        }

        [data-testid="stForm"] textarea:focus,
        [data-testid="stForm"] textarea:focus-visible,
        [data-testid="stForm"] input:focus,
        [data-testid="stForm"] input:focus-visible {
            outline: none !important;
            box-shadow: none !important;
        }

        [data-testid="stForm"] [data-testid="InputInstructions"] {
            border: none !important;
            outline: none !important;
            box-shadow: none !important;
            background: transparent !important;
        }

        [data-baseweb="input"] input,
        [data-baseweb="base-input"] input,
        [data-baseweb="select"] input,
        textarea,
        input {
            color: #3f3125 !important;
            -webkit-text-fill-color: #3f3125 !important;
        }

        input::placeholder, textarea::placeholder {
            color: rgba(99, 71, 50, 0.58) !important;
        }

        label, [data-testid="stWidgetLabel"] {
            color: #5a4333 !important;
            font-weight: 600;
        }

        .stButton > button, [data-testid="baseButton-primary"] {
            border-radius: 999px;
            background: linear-gradient(135deg, #c48e64 0%, #d6a27a 100%);
            color: white;
            border: none;
            font-weight: 700;
            padding: 0.55rem 1rem;
            box-shadow: 0 12px 20px rgba(196, 142, 100, 0.22);
        }

        .stButton > button:hover, [data-testid="baseButton-primary"]:hover {
            background: linear-gradient(135deg, #b57c52 0%, #c78f66 100%);
        }

        .table-shell {
            background: rgba(255, 249, 242, 0.88);
            border: 1px solid rgba(111, 77, 53, 0.10);
            border-radius: 24px;
            padding: 0.7rem;
            box-shadow: 0 10px 24px rgba(99, 71, 50, 0.06);
        }

        .table-scroller {
            overflow-x: auto;
            border-radius: 18px;
            padding-bottom: 0.1rem;
        }

        table.portfolio-table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            overflow: hidden;
            border-radius: 18px;
            background: rgba(255, 252, 247, 0.98);
        }

        table.portfolio-table thead th {
            background: linear-gradient(180deg, #f2e4d1 0%, #ecd9c2 100%);
            color: #6d4e38;
            font-size: 0.82rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            font-weight: 700;
            padding: 1rem 0.9rem;
            line-height: 1.3;
            border-bottom: 1px solid rgba(111, 77, 53, 0.12);
            white-space: nowrap;
            vertical-align: middle;
        }

        table.portfolio-table thead th:first-child {
            border-top-left-radius: 18px;
        }

        table.portfolio-table thead th:last-child {
            border-top-right-radius: 18px;
        }

        table.portfolio-table tbody td {
            padding: 0.95rem 0.9rem;
            line-height: 1.35;
            border-bottom: 1px solid rgba(111, 77, 53, 0.08);
            color: #4a392c;
            background: rgba(255, 252, 247, 0.96);
            white-space: nowrap;
            vertical-align: middle;
        }

        table.portfolio-table tbody tr:nth-child(even) td {
            background: rgba(248, 238, 226, 0.72);
        }

        table.portfolio-table tbody tr:hover td {
            background: rgba(242, 228, 209, 0.78);
        }

        table.portfolio-table tbody tr:last-child td:first-child {
            border-bottom-left-radius: 18px;
        }

        table.portfolio-table tbody tr:last-child td:last-child {
            border-bottom-right-radius: 18px;
        }

        h1, h2, h3 {
            color: #5b412f;
            letter-spacing: -0.03em;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_page_header(title: str, subtitle: str, kicker: str = "Portfolio") -> None:
    """Render the reusable hero header used at the top of each page."""
    st.markdown(
        f"""
        <section class="hero-card">
            <div class="hero-kicker">{kicker}</div>
            <h1 class="hero-title">{title}</h1>
            <p class="hero-subtitle">{subtitle}</p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_data_table(df: pd.DataFrame, hide_index: bool = True) -> None:
    """Render a styled HTML table that matches the app's warm card-based theme."""
    if df is None or df.empty:
        st.info("No data to display.")
        return

    table_df = df.copy()
    quantity_columns = {
        "Shares",
        "Remaining Shares",
        "Units",
        "Total Shares",
    }

    for column in table_df.columns:
        if pd.api.types.is_datetime64_any_dtype(table_df[column]):
            table_df[column] = table_df[column].dt.strftime("%Y-%m-%d")
        elif column in quantity_columns and pd.api.types.is_numeric_dtype(table_df[column]):
            table_df[column] = table_df[column].map(format_compact_quantity)
        elif pd.api.types.is_float_dtype(table_df[column]):
            table_df[column] = table_df[column].map(
                lambda value: "" if pd.isna(value) else f"{value:,.2f}"
            )

    html = table_df.to_html(
        index=not hide_index,
        classes="portfolio-table",
        border=0,
        escape=False,
    )

    st.markdown(
        f"""
        <div class="table-shell">
            <div class="table-scroller">
                {html}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
