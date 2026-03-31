"""Read/write helpers for trades, dividends, watchlist items, and derived master files.

This module is the persistence layer for the app. Pages should prefer calling these
helpers rather than writing CSV files directly so normalization and migrations stay
consistent in one place.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.config import (
    DATA_DIR,
    DATA_PATH,
    DIVIDEND_PATH,
    RAW_UPLOAD_DIR,
    TRADE_PATH,
    TRANSACTION_COLUMNS,
    WATCHLIST_COLUMNS,
    WATCHLIST_PATH,
)
from src.importers.moomoo import deduplicate_transactions, transform_moomoo_to_app_schema


def _empty_transactions_df() -> pd.DataFrame:
    return pd.DataFrame(columns=TRANSACTION_COLUMNS)


def _normalize_transactions(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce uploaded/appended transaction data into the app's canonical schema."""
    if df is None or df.empty:
        return _empty_transactions_df()

    normalized = df.copy()
    for column in TRANSACTION_COLUMNS:
        if column not in normalized.columns:
            normalized[column] = ""

    normalized = normalized[TRANSACTION_COLUMNS]
    normalized["Date"] = pd.to_datetime(normalized["Date"], errors="coerce")
    normalized = normalized.dropna(subset=["Date"]).copy()
    normalized["Ticker"] = normalized["Ticker"].astype(str).str.strip().str.upper()
    normalized["Type"] = normalized["Type"].astype(str).str.strip().str.title()
    normalized["Currency"] = normalized["Currency"].astype(str).str.strip().str.upper()

    for column in ["Units", "Price", "Fee"]:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce").fillna(0.0)

    normalized = normalized.sort_values("Date").reset_index(drop=True)
    return normalized


def _read_transactions_csv(path: str) -> pd.DataFrame:
    csv_path = Path(path)
    if not csv_path.exists():
        return _empty_transactions_df()
    return _normalize_transactions(pd.read_csv(csv_path))


def _empty_watchlist_df() -> pd.DataFrame:
    return pd.DataFrame(columns=WATCHLIST_COLUMNS)


def _normalize_watchlist(df: pd.DataFrame) -> pd.DataFrame:
    """Apply the same cleanup rules whenever watchlist rows are read or written."""
    if df is None or df.empty:
        return _empty_watchlist_df()

    normalized = df.copy()
    for column in WATCHLIST_COLUMNS:
        if column not in normalized.columns:
            normalized[column] = ""

    normalized = normalized[WATCHLIST_COLUMNS]
    normalized["Date Added"] = pd.to_datetime(normalized["Date Added"], errors="coerce")
    normalized = normalized.dropna(subset=["Date Added"]).copy()
    normalized["Ticker"] = normalized["Ticker"].astype(str).str.strip().str.upper()
    normalized["Watch Type"] = normalized["Watch Type"].astype(str).replace({"": "Buy"}).str.strip().str.title()
    normalized["Priority"] = normalized["Priority"].astype(str).str.strip().str.title()
    normalized["Status"] = normalized["Status"].astype(str).str.strip().str.title()
    normalized["Notes"] = normalized["Notes"].astype(str).fillna("").str.strip()
    normalized["Target Price"] = pd.to_numeric(normalized["Target Price"], errors="coerce").fillna(0.0)
    normalized["Fair Value"] = pd.to_numeric(normalized["Fair Value"], errors="coerce")
    normalized = normalized.sort_values(["Watch Type", "Status", "Priority", "Date Added", "Ticker"]).reset_index(drop=True)
    return normalized


def _read_watchlist_csv(path: str = WATCHLIST_PATH) -> pd.DataFrame:
    csv_path = Path(path)
    if not csv_path.exists():
        return _empty_watchlist_df()
    return _normalize_watchlist(pd.read_csv(csv_path))


def _write_watchlist_csv(df: pd.DataFrame, path: str = WATCHLIST_PATH) -> None:
    output = _normalize_watchlist(df)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    if output.empty:
        _empty_watchlist_df().to_csv(path, index=False)
        return

    serializable = output.copy()
    serializable["Date Added"] = serializable["Date Added"].dt.strftime("%Y-%m-%d")
    serializable.to_csv(path, index=False)


def _write_transactions_csv(df: pd.DataFrame, path: str) -> None:
    output = _normalize_transactions(df)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    if output.empty:
        _empty_transactions_df().to_csv(path, index=False)
        return

    serializable = output.copy()
    serializable["Date"] = serializable["Date"].dt.strftime("%Y-%m-%d %H:%M:%S")
    serializable.to_csv(path, index=False)


def migrate_legacy_transactions() -> None:
    """Split the old single `transactions.csv` layout into trade/dividend source files."""
    trades_exist = Path(TRADE_PATH).exists()
    dividends_exist = Path(DIVIDEND_PATH).exists()

    if trades_exist or dividends_exist:
        return

    legacy_df = _read_transactions_csv(DATA_PATH)
    trade_df = legacy_df[legacy_df["Type"].isin(["Buy", "Sell"])].copy()
    dividend_df = legacy_df[legacy_df["Type"] == "Dividend"].copy()

    _write_transactions_csv(trade_df, TRADE_PATH)
    _write_transactions_csv(dividend_df, DIVIDEND_PATH)


def rebuild_transactions_master() -> pd.DataFrame:
    """Recreate the combined transaction file from the trade and dividend sources."""
    trade_df = _read_transactions_csv(TRADE_PATH)
    dividend_df = _read_transactions_csv(DIVIDEND_PATH)
    frames = [df for df in [trade_df, dividend_df] if not df.empty]
    combined = pd.concat(frames, ignore_index=True) if frames else _empty_transactions_df()
    _write_transactions_csv(combined, DATA_PATH)
    return _read_transactions_csv(DATA_PATH)


def ensure_data_files() -> None:
    """Create required folders/files and run one-time migration if needed."""
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
    Path(RAW_UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    migrate_legacy_transactions()

    for path in [TRADE_PATH, DIVIDEND_PATH]:
        if not Path(path).exists():
            _write_transactions_csv(_empty_transactions_df(), path)

    if not Path(WATCHLIST_PATH).exists():
        _write_watchlist_csv(_empty_watchlist_df(), WATCHLIST_PATH)

    if not Path(DATA_PATH).exists():
        rebuild_transactions_master()


def save_uploaded_raw_file(raw_df: pd.DataFrame, file_name_stem: str) -> Path:
    ensure_data_files()
    safe_name = Path(file_name_stem).stem.strip()
    if not safe_name:
        raise ValueError("Please enter a valid file name.")

    raw_path = Path(RAW_UPLOAD_DIR) / f"{safe_name}.csv"
    raw_df.to_csv(raw_path, index=False)
    return raw_path


def import_moomoo_transactions(raw_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """Transform a broker export, deduplicate it against imported trades, and persist it."""
    ensure_data_files()
    cleaned_df = _normalize_transactions(transform_moomoo_to_app_schema(raw_df))
    existing_trades = _read_transactions_csv(TRADE_PATH)
    net_new_df = deduplicate_transactions(cleaned_df, existing_trades)
    updated_trades = pd.concat([existing_trades, net_new_df], ignore_index=True)
    _write_transactions_csv(updated_trades, TRADE_PATH)
    rebuild_transactions_master()
    return cleaned_df, net_new_df, len(existing_trades)


def append_dividend_transaction(
    *,
    date,
    ticker: str,
    shares: float,
    dividend_per_share: float,
    fee: float,
    currency: str,
) -> pd.DataFrame:
    """Append one manual dividend row and then rebuild the combined transaction file."""
    ensure_data_files()
    dividend_row = pd.DataFrame([
        {
            "Date": pd.to_datetime(date),
            "Ticker": ticker,
            "Type": "Dividend",
            "Units": shares,
            "Price": dividend_per_share,
            "Fee": fee,
            "Currency": currency,
        }
    ])
    existing_dividends = _read_transactions_csv(DIVIDEND_PATH)
    updated_dividends = pd.concat([existing_dividends, dividend_row], ignore_index=True)
    _write_transactions_csv(updated_dividends, DIVIDEND_PATH)
    return rebuild_transactions_master()


def delete_last_transaction(source: str) -> bool:
    ensure_data_files()
    source_map = {
        "Trades": TRADE_PATH,
        "Dividends": DIVIDEND_PATH,
    }
    path = source_map[source]
    df = _read_transactions_csv(path)
    if df.empty:
        return False

    _write_transactions_csv(df.iloc[:-1], path)
    rebuild_transactions_master()
    return True


def load_source_transactions(source: str) -> pd.DataFrame:
    ensure_data_files()
    source_map = {
        "Trades": TRADE_PATH,
        "Dividends": DIVIDEND_PATH,
    }
    return _read_transactions_csv(source_map[source])


def load_transactions(path: str = DATA_PATH) -> pd.DataFrame:
    """Load transactions and enrich them with a precomputed cash impact column."""
    ensure_data_files()
    if path == DATA_PATH:
        df = rebuild_transactions_master()
    else:
        df = _read_transactions_csv(path)

    # Compute TotalCost depending on Type
    def compute_total(row):
        if row["Type"] == "Buy":
            return row["Units"] * row["Price"] + row["Fee"]
        if row["Type"] == "Sell":
            return row["Units"] * row["Price"] - row["Fee"]
        return row["Units"] * row["Price"] - row["Fee"]

    df["TotalCost"] = df.apply(compute_total, axis=1)
    return df


def load_watchlist(path: str = WATCHLIST_PATH) -> pd.DataFrame:
    ensure_data_files()
    return _read_watchlist_csv(path)


def append_watchlist_item(
    *,
    date_added,
    ticker: str,
    watch_type: str,
    target_price: float,
    fair_value: float | None,
    priority: str,
    notes: str,
) -> pd.DataFrame:
    """Add a watchlist row to the source CSV after normalizing the payload."""
    ensure_data_files()
    watchlist_row = pd.DataFrame([
        {
            "Date Added": pd.to_datetime(date_added),
            "Ticker": ticker,
            "Watch Type": watch_type,
            "Target Price": target_price,
            "Fair Value": fair_value,
            "Priority": priority,
            "Status": "",
            "Notes": notes,
        }
    ])
    existing_watchlist = _read_watchlist_csv(WATCHLIST_PATH)
    updated_watchlist = pd.concat([existing_watchlist, watchlist_row], ignore_index=True)
    _write_watchlist_csv(updated_watchlist, WATCHLIST_PATH)
    return load_watchlist()


def update_watchlist_item(
    *,
    original_ticker: str,
    original_date_added: str,
    watch_type: str,
    target_price: float,
    fair_value: float | None,
    priority: str,
    notes: str,
) -> bool:
    """Update one watchlist row identified by ticker + original date."""
    ensure_data_files()
    watchlist_df = _read_watchlist_csv(WATCHLIST_PATH)
    if watchlist_df.empty:
        return False

    matching_mask = (
        (watchlist_df["Ticker"] == original_ticker.strip().upper()) &
        (watchlist_df["Date Added"].dt.strftime("%Y-%m-%d") == original_date_added)
    )
    if not matching_mask.any():
        return False

    watchlist_df.loc[matching_mask, "Watch Type"] = watch_type
    watchlist_df.loc[matching_mask, "Target Price"] = target_price
    watchlist_df.loc[matching_mask, "Fair Value"] = fair_value
    watchlist_df.loc[matching_mask, "Priority"] = priority
    watchlist_df.loc[matching_mask, "Notes"] = notes
    _write_watchlist_csv(watchlist_df, WATCHLIST_PATH)
    return True


def delete_watchlist_item(ticker: str, date_added: str) -> bool:
    ensure_data_files()
    watchlist_df = _read_watchlist_csv(WATCHLIST_PATH)
    if watchlist_df.empty:
        return False

    matching_mask = (
        (watchlist_df["Ticker"] == ticker.strip().upper()) &
        (watchlist_df["Date Added"].dt.strftime("%Y-%m-%d") == date_added)
    )
    if not matching_mask.any():
        return False

    updated_watchlist = watchlist_df.loc[~matching_mask].copy()
    _write_watchlist_csv(updated_watchlist, WATCHLIST_PATH)
    return True
