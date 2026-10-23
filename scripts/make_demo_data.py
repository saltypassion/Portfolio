"""Generate the sample portfolio in demo_data/ (used when there is no personal data/ folder).

The trades are made up, but priced at real historical closes from Yahoo Finance so charts and
P/L look realistic. Dividends are derived from real dividend history with 30% US withholding.
The open option is a real listed contract so it can be valued live.

Usage:
    python3 scripts/make_demo_data.py
"""

from __future__ import annotations

import math
import os
import sys
from datetime import date, timedelta

import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.config import DEMO_DATA_DIR, OPTION_COLUMNS, TRANSACTION_COLUMNS, WATCHLIST_COLUMNS

STOCK_FEE = 1.08
OPTION_FEE = 3.47
US_WITHHOLDING = 0.30

# (date, ticker, side, shares)
STOCK_TRADES = [
    ("2024-02-05", "VTI", "Buy", 10),
    ("2024-03-12", "MSFT", "Buy", 5),
    ("2024-05-20", "KO", "Buy", 20),
    ("2024-08-06", "GOOG", "Buy", 8),
    ("2024-11-14", "JNJ", "Buy", 6),
    ("2025-04-08", "AAPL", "Buy", 10),
    ("2025-06-02", "MSFT", "Buy", 3),
    ("2025-09-15", "AAPL", "Sell", 5),
    ("2026-02-10", "VTI", "Buy", 5),
]

# Closed short puts: (underlying, sold on, expiry, strike as fraction of spot, premium, close)
# close is ("buyback", date, price) or ("expire",). Assignment is decided by the expiry close.
SHORT_PUTS = [
    ("KO", "2026-03-02", "2026-03-20", None, 1.20, ("expire",)),
    ("MSFT", "2026-05-04", "2026-06-18", 0.92, 6.10, ("buyback", "2026-06-01", 1.40)),
    ("NVDA", "2026-07-06", "2026-08-21", 0.85, 2.30, ("expire",)),
    ("GOOG", "2026-08-10", "2026-09-18", 0.95, 3.10, ("buyback", "2026-09-01", 5.60)),
]

WATCHLIST = [
    ("2026-09-01", "AMZN", "Buy", 0.90, 1.15, "High", "Wait for a pullback to add"),
    ("2026-09-15", "COST", "Buy", 0.92, 1.05, "Medium", "Quality compounder, rarely cheap"),
    ("2026-10-01", "AAPL", "Sell", 1.08, None, "Low", "Trim remaining shares near target"),
]


def close_on(ticker: str, day: str) -> tuple[pd.Timestamp, float]:
    """First available close on or after the given day."""
    start = pd.Timestamp(day)
    history = yf.Ticker(ticker).history(start=start, end=start + timedelta(days=7))
    if history.empty:
        raise RuntimeError(f"No price for {ticker} around {day}")
    return history.index[0].tz_localize(None).normalize(), float(history["Close"].iloc[0])


def stock_rows() -> list[dict]:
    rows = []
    for day, ticker, side, shares in STOCK_TRADES:
        traded_on, price = close_on(ticker, day)
        rows.append({
            "Date": traded_on + timedelta(hours=10, minutes=30),
            "Ticker": ticker,
            "Type": side,
            "Units": float(shares),
            "Price": round(price, 2),
            "Fee": STOCK_FEE,
            "Currency": "USD",
        })
    return rows


def contract_code(underlying: str, expiry: pd.Timestamp, strike: float) -> str:
    return f"{underlying}{expiry:%y%m%d}P{round(strike * 1000)}"


def option_fill(day, underlying, expiry, strike, side, price, fee) -> dict:
    return {
        "Date": pd.Timestamp(day),
        "Contract": contract_code(underlying, expiry, strike),
        "Underlying": underlying,
        "Expiry": expiry,
        "Right": "Put",
        "Strike": strike,
        "Side": side,
        "Contracts": 1.0,
        "Price": price,
        "Fee": fee,
        "Currency": "USD",
    }


def option_rows(stocks: list[dict]) -> list[dict]:
    fills = []
    for underlying, sold_on, expiry_day, moneyness, premium, close in SHORT_PUTS:
        expiry = pd.Timestamp(expiry_day)
        sold_at, spot = close_on(underlying, sold_on)
        if moneyness is None:
            # Strike just above the expiry close, so this put ends up assigned.
            _, expiry_close = close_on(underlying, expiry_day)
            strike = float(math.ceil(expiry_close) + 1)
        else:
            strike = float(round(spot * moneyness / 5) * 5)

        fills.append(option_fill(sold_at + timedelta(hours=11), underlying, expiry, strike, "Sell", premium, OPTION_FEE))

        if close[0] == "buyback":
            fills.append(option_fill(pd.Timestamp(close[1]) + timedelta(hours=10), underlying, expiry, strike, "Buy", close[2], OPTION_FEE))
            continue

        # moomoo closes expiring contracts with a $0 fill the next morning.
        fills.append(option_fill(expiry + timedelta(days=1, hours=1), underlying, expiry, strike, "Buy", 0.0, 0.0))
        _, expiry_close = close_on(underlying, expiry_day)
        if expiry_close < strike:
            stocks.append({
                "Date": expiry + timedelta(hours=16),
                "Ticker": underlying,
                "Type": "Buy",
                "Units": 100.0,
                "Price": strike,
                "Fee": 0.0,
                "Currency": "USD",
            })

    fills.append(open_put_fill())
    return fills


def open_put_fill() -> dict:
    """Sell a real, currently listed ~7% out-of-the-money MSFT put a few weeks before expiry."""
    ticker = yf.Ticker("MSFT")
    today = pd.Timestamp(date.today())
    expiries = [pd.Timestamp(e) for e in ticker.options if pd.Timestamp(e) >= today + timedelta(days=21)]
    expiry = expiries[0]
    spot = float(ticker.history(period="5d")["Close"].iloc[-1])
    puts = ticker.option_chain(f"{expiry:%Y-%m-%d}").puts
    puts = puts[(puts["lastPrice"] > 0) & (puts["strike"] <= spot * 0.93)]
    contract = puts.sort_values("strike").iloc[-1]
    sold_on = today - timedelta(days=10)
    return option_fill(
        sold_on + timedelta(hours=11), "MSFT", expiry, float(contract["strike"]), "Sell",
        round(float(contract["lastPrice"]) * 1.4, 2), OPTION_FEE,
    )


def dividend_rows(stocks: pd.DataFrame) -> list[dict]:
    rows = []
    signed = stocks["Units"].where(stocks["Type"] == "Buy", -stocks["Units"])
    for ticker in stocks["Ticker"].unique():
        trades = stocks[stocks["Ticker"] == ticker].assign(Signed=signed)
        history = yf.Ticker(ticker).dividends
        for ex_date, per_share in history.items():
            ex_date = ex_date.tz_localize(None).normalize()
            if ex_date.date() > date.today():
                continue
            shares = trades.loc[trades["Date"] < ex_date, "Signed"].sum()
            if shares <= 0:
                continue
            gross = shares * per_share
            rows.append({
                "Date": ex_date,
                "Ticker": ticker,
                "Type": "Dividend",
                "Units": float(shares),
                "Price": round(float(per_share), 6),
                "Fee": round(gross * US_WITHHOLDING, 2),
                "Currency": "USD",
            })
    return rows


def watchlist_rows() -> list[dict]:
    rows = []
    for added, ticker, side, target_ratio, fair_ratio, priority, notes in WATCHLIST:
        spot = float(yf.Ticker(ticker).history(period="5d")["Close"].iloc[-1])
        rows.append({
            "Date Added": added,
            "Ticker": ticker,
            "Watch Type": side,
            "Target Price": round(spot * target_ratio, 0),
            "Fair Value": round(spot * fair_ratio, 0) if fair_ratio else None,
            "Priority": priority,
            "Status": "",
            "Notes": notes,
        })
    return rows


def main() -> None:
    os.makedirs(DEMO_DATA_DIR, exist_ok=True)
    stocks = stock_rows()
    options = option_rows(stocks)
    trades = pd.DataFrame(stocks, columns=TRANSACTION_COLUMNS).sort_values("Date")
    dividends = pd.DataFrame(dividend_rows(trades), columns=TRANSACTION_COLUMNS).sort_values("Date")

    timestamp = "%Y-%m-%d %H:%M:%S"
    trades.to_csv(os.path.join(DEMO_DATA_DIR, "trades.csv"), index=False, date_format=timestamp)
    dividends.to_csv(os.path.join(DEMO_DATA_DIR, "dividends.csv"), index=False, date_format=timestamp)
    pd.DataFrame(options, columns=OPTION_COLUMNS).sort_values("Date").to_csv(
        os.path.join(DEMO_DATA_DIR, "options.csv"), index=False, date_format=timestamp
    )
    pd.DataFrame(watchlist_rows(), columns=WATCHLIST_COLUMNS).to_csv(
        os.path.join(DEMO_DATA_DIR, "watchlist.csv"), index=False
    )
    print(f"Wrote {len(trades)} trades, {len(dividends)} dividends and {len(options)} option fills to {DEMO_DATA_DIR}")


if __name__ == "__main__":
    main()
