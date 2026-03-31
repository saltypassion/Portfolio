"""Market-data and profile lookups used by holdings, watchlist, and detail pages."""

import yfinance as yf
import pandas as pd
import streamlit as st

@st.cache_data(ttl=120)  # cache for 2 minutes to avoid hitting API limits
def get_latest_prices(tickers):
    """Fetch latest close prices while handling yfinance's inconsistent response shapes."""

    if not tickers:
        return pd.Series(dtype=float)

    tickers = [str(t).strip().upper() for t in tickers if str(t).strip()]
    if not tickers:
        return pd.Series(dtype=float)

    data = yf.download(
        tickers,
        period="1d",
        group_by="ticker",
        progress=False
    )

    if data is None or len(data) == 0:
        return pd.Series({ticker: 0.0 for ticker in tickers})

    def extract_close_from_download(downloaded, ticker):
        if downloaded is None or len(downloaded) == 0:
            return 0.0

        if isinstance(downloaded.columns, pd.MultiIndex):
            level0 = list(downloaded.columns.get_level_values(0))
            level1 = list(downloaded.columns.get_level_values(1))

            # Shape: ('Close', 'AAPL')
            if "Close" in level0:
                close_series = downloaded["Close"]
                if hasattr(close_series, "columns"):
                    if ticker in close_series.columns:
                        value = close_series[ticker].iloc[-1]
                    else:
                        value = close_series.iloc[-1, 0]
                else:
                    value = close_series.iloc[-1]
                return float(value) if pd.notna(value) else 0.0

            # Shape: ('AAPL', 'Close')
            if ticker in level0 and "Close" in level1:
                value = downloaded[ticker]["Close"].iloc[-1]
                return float(value) if pd.notna(value) else 0.0

            return 0.0

        if "Close" in downloaded.columns:
            value = downloaded["Close"].iloc[-1]
            return float(value) if pd.notna(value) else 0.0

        return 0.0

    # Case 1 — single ticker
    if len(tickers) == 1:
        ticker = tickers[0]
        try:
            close_price = extract_close_from_download(data, ticker)
        except Exception:
            close_price = 0.0

        return pd.Series({ticker: close_price})

    # Case 2 — multiple tickers
    prices = {}

    for ticker in tickers:
        try:
            prices[ticker] = extract_close_from_download(data, ticker)
        except Exception:
            prices[ticker] = 0.0

    return pd.Series(prices)

@st.cache_data(ttl=3600)  # cache for 1 hour
def get_price_history(ticker: str, period: str = "1y") -> pd.DataFrame:
    """Fetch historical OHLCV data for a single ticker."""
    return yf.Ticker(ticker).history(period=period)


@st.cache_data(ttl=21600)  # cache for 6 hours
def get_ticker_profiles(tickers: tuple[str, ...]) -> pd.DataFrame:
    """Fetch company/fund metadata for a list of tickers.

    ETFs often lack stock-style sector/industry fields, so this function also exposes
    fund-category/family fields and uses them as fallbacks where helpful.
    """
    rows = []

    for ticker in tickers:
        try:
            info = yf.Ticker(ticker).info or {}
        except Exception:
            info = {}

        quote_type = (info.get("quoteType") or "").upper()
        fund_category = (
            info.get("fundCategory")
            or info.get("category")
            or info.get("categoryName")
            or ""
        )
        fund_family = (
            info.get("fundFamily")
            or info.get("family")
            or info.get("fundSponsor")
            or ""
        )
        sector = info.get("sector") or ""
        industry = info.get("industry") or ""

        # ETFs often do not have stock-style sector/industry values.
        # Fall back to fund metadata so the UI can still show something useful.
        if quote_type in {"ETF", "MUTUALFUND"}:
            sector = sector or fund_category
            industry = industry or fund_family

        rows.append({
            "Ticker": ticker,
            "Name": info.get("shortName") or info.get("longName") or ticker,
            "Type": quote_type,
            "Sector": sector,
            "Industry": industry,
            "Fund Category": fund_category,
            "Fund Family": fund_family,
        })

    return pd.DataFrame(rows)
