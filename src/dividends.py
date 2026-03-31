"""Helpers for estimating dividend receipts from historical distributions."""

from __future__ import annotations

import pandas as pd
import yfinance as yf


def build_daily_positions(transactions: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Turn signed transaction changes into a daily shares-held time series."""
    tx = transactions[transactions["Ticker"] == ticker].copy()

    if tx.empty:
        return pd.DataFrame(columns=["Date", "Shares"])

    tx["DateOnly"] = pd.to_datetime(tx["Date"]).dt.normalize()

    daily = (
        tx.groupby("DateOnly", as_index=False)["SignedQuantity"]
        .sum()
        .rename(columns={"DateOnly": "Date", "SignedQuantity": "NetSharesChange"})
        .sort_values("Date")
    )

    daily["Shares"] = daily["NetSharesChange"].cumsum()

    all_dates = pd.date_range(
        start=daily["Date"].min(),
        end=pd.Timestamp.today().normalize(),
        freq="D"
    )

    daily = (
        daily.set_index("Date")[["Shares"]]
        .reindex(all_dates)
        .ffill()
        .fillna(0)
        .rename_axis("Date")
        .reset_index()
    )

    return daily


def get_dividend_history(ticker: str) -> pd.DataFrame:
    """Load historical dividend-per-share events from Yahoo Finance."""
    data = yf.Ticker(ticker).dividends

    if data is None or len(data) == 0:
        return pd.DataFrame(columns=["Date", "DividendPerShare"])

    df = data.reset_index()
    df.columns = ["Date", "DividendPerShare"]
    df["Date"] = pd.to_datetime(df["Date"]).dt.normalize()

    return df


def default_dividend_tax_rate(ticker: str) -> float:
    # Simple default until country/ticker-specific withholding rules are modeled.
    if ticker.endswith(".SI"):
        return 0.0
    return 0.30


def compute_dividends(
    transactions: pd.DataFrame,
    ticker: str,
    tax_rate: float | None = None,
    extra_fee_per_dividend: float = 0.0,
) -> pd.DataFrame:
    """Estimate gross/net dividends by matching ex-dividend dates to held shares."""
    positions = build_daily_positions(transactions, ticker)
    dividends = get_dividend_history(ticker)

    if positions.empty or dividends.empty:
        return pd.DataFrame(columns=[
            "Date",
            "Ticker",
            "SharesHeld",
            "DividendPerShare",
            "GrossDividend",
            "TaxRate",
            "TaxAmount",
            "ExtraFee",
            "NetDividend",
        ])

    out = dividends.merge(
        positions.rename(columns={"Shares": "SharesHeld"}),
        on="Date",
        how="left"
    )

    out["SharesHeld"] = out["SharesHeld"].fillna(0)

    # Ignore dividend events where the portfolio held no shares on the event date.
    out = out[out["SharesHeld"] > 0].copy()

    applied_tax = default_dividend_tax_rate(ticker) if tax_rate is None else tax_rate

    out["Ticker"] = ticker
    out["GrossDividend"] = out["SharesHeld"] * out["DividendPerShare"]
    out["TaxRate"] = applied_tax
    out["TaxAmount"] = out["GrossDividend"] * out["TaxRate"]
    out["ExtraFee"] = extra_fee_per_dividend
    out["NetDividend"] = out["GrossDividend"] - out["TaxAmount"] - out["ExtraFee"]

    return out[[
        "Date",
        "Ticker",
        "SharesHeld",
        "DividendPerShare",
        "GrossDividend",
        "TaxRate",
        "TaxAmount",
        "ExtraFee",
        "NetDividend",
    ]]
