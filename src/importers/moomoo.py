"""Transform raw Moomoo exports into the app's transaction schema."""

import pandas as pd

FEE_COLUMNS = [
    "Platform Fees",
    "Settlement Fees",
    "Consumption Tax",
    "SEC Fees",
    "Trading Activity Fees",
    "Consolidated Audit Trail Fees",
]


def clean_numeric(series: pd.Series) -> pd.Series:
    """Strip broker-export formatting before numeric conversion."""
    return (
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("$", "", regex=False)
        .str.strip()
        .replace({"": None, "nan": None, "None": None, "--": None})
        .pipe(pd.to_numeric, errors="coerce")
    )


def transform_moomoo_to_app_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Map Moomoo trade columns into the app's canonical transaction columns."""
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    required = ["Side", "Symbol", "Fill Qty", "Fill Price", "Fill Time"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df = df[df["Fill Qty"].notna()]
    df = df[df["Fill Time"].notna()].copy()

    out = pd.DataFrame()
    out["Date"] = pd.to_datetime(df["Fill Time"], errors="coerce")
    out["Ticker"] = df["Symbol"].astype(str).str.strip().str.upper()
    out["Type"] = df["Side"].astype(str).str.strip().str.title()
    out["Units"] = clean_numeric(df["Fill Qty"]).fillna(0)
    out["Price"] = clean_numeric(df["Fill Price"]).fillna(0)

    # Moomoo spreads fees across multiple columns, so collect them into one total.
    fee_total = pd.Series(0.0, index=df.index)
    for col in FEE_COLUMNS:
        if col in df.columns:
            fee_total = fee_total.add(clean_numeric(df[col]).fillna(0.0), fill_value=0.0)
    out["Fee"] = fee_total

    if "Currency.1" in df.columns:
        out["Currency"] = df["Currency.1"].astype(str).str.strip().str.upper()
    elif "Currency" in df.columns:
        out["Currency"] = df["Currency"].astype(str).str.strip().str.upper()
    else:
        out["Currency"] = ""

    out = out.dropna(subset=["Date"])
    out = out.sort_values("Date").reset_index(drop=True)

    return out


def deduplicate_transactions(new_df: pd.DataFrame, existing_df: pd.DataFrame) -> pd.DataFrame:
    """
    Remove rows from new_df that already exist in existing_df.
    Matches on Date, Ticker, Type, Units, and Price.
    Returns only the net-new rows to be appended.
    """
    if existing_df.empty:
        return new_df

    match_cols = ["Date", "Ticker", "Type", "Units", "Price", "Fee", "Currency"]

    existing_keys = existing_df[match_cols].copy()
    existing_keys["Date"] = pd.to_datetime(existing_keys["Date"])

    new_keys = new_df[match_cols].copy()
    new_keys["Date"] = pd.to_datetime(new_keys["Date"])

    merged = new_keys.merge(existing_keys, on=match_cols, how="left", indicator=True)
    is_new = merged["_merge"] == "left_only"

    return new_df[is_new.values].reset_index(drop=True)
