"""Option trade analytics: group fills into trades and measure what each one earned."""

from __future__ import annotations

import pandas as pd

from src.config import OPTION_MULTIPLIER

TRADE_COLUMNS = [
    "Contract",
    "Underlying",
    "Strategy",
    "Expiry",
    "Strike",
    "Contracts",
    "Opened",
    "Closed",
    "Opening Value",
    "Closing Value",
    "Fees",
    "Net Cash",
    "Outcome",
    "Collateral",
]

# A short put is assigned if the underlying is bought at the strike within this many days of expiry.
ASSIGNMENT_WINDOW_DAYS = 3


def yahoo_option_symbol(row: pd.Series) -> str:
    """Build Yahoo's contract symbol, e.g. XBI 2026-11-20 143 put -> "XBI261120P00143000"."""
    right = "P" if row["Right"] == "Put" else "C"
    return f"{row['Underlying']}{row['Expiry']:%y%m%d}{right}{round(row['Strike'] * 1000):08d}"


def _outcome(trade: dict, closing_fill: pd.Series, stock_trades: pd.DataFrame) -> str:
    """Name how a closed trade ended: bought back / sold, expired worthless, or assigned/exercised."""
    if closing_fill["Price"] > 0 or closing_fill["Date"].normalize() < trade["Expiry"]:
        return "Bought back" if trade["Side"] == "Sell" else "Sold"

    # moomoo closes expiring contracts with a $0 fill. If shares changed hands at the strike, it was assigned.
    expected_stock_side = {
        ("Sell", "Put"): "Buy",
        ("Sell", "Call"): "Sell",
        ("Buy", "Put"): "Sell",
        ("Buy", "Call"): "Buy",
    }[(trade["Side"], trade["Right"])]
    window_end = trade["Expiry"] + pd.Timedelta(days=ASSIGNMENT_WINDOW_DAYS)
    stock_dates = stock_trades["Date"].dt.normalize()
    assigned = stock_trades[
        (stock_trades["Ticker"] == trade["Underlying"])
        & (stock_trades["Type"] == expected_stock_side)
        & ((stock_trades["Price"] - trade["Strike"]).abs() < 0.005)
        & (stock_dates >= trade["Expiry"])
        & (stock_dates <= window_end)
    ]
    if not assigned.empty:
        return "Assigned" if trade["Side"] == "Sell" else "Exercised"
    return "Expired"


def build_option_trades(fills: pd.DataFrame, stock_trades: pd.DataFrame | None = None) -> pd.DataFrame:
    """Group option fills into trades: each runs from opening a contract until the position is flat again."""
    if fills.empty:
        return pd.DataFrame(columns=TRADE_COLUMNS)

    stock_trades = stock_trades if stock_trades is not None else pd.DataFrame(
        columns=["Date", "Ticker", "Type", "Price"]
    )
    stock_trades = stock_trades.assign(Date=pd.to_datetime(stock_trades["Date"]))

    trades = []
    for contract, contract_fills in fills.sort_values("Date").groupby("Contract", sort=False):
        position = 0.0
        trade = None
        for _, fill in contract_fills.iterrows():
            signed = fill["Contracts"] if fill["Side"] == "Buy" else -fill["Contracts"]
            value = fill["Price"] * fill["Contracts"] * OPTION_MULTIPLIER

            if position == 0:
                trade = {
                    "Contract": contract,
                    "Underlying": fill["Underlying"],
                    "Right": fill["Right"],
                    "Side": fill["Side"],
                    "Strategy": f"{'Short' if fill['Side'] == 'Sell' else 'Long'} {fill['Right']}",
                    "Expiry": fill["Expiry"],
                    "Strike": fill["Strike"],
                    "Contracts": 0.0,
                    "Opened": fill["Date"],
                    "Closed": pd.NaT,
                    "Opening Value": 0.0,
                    "Closing Value": 0.0,
                    "Fees": 0.0,
                    "Net Cash": 0.0,
                    "Outcome": "Open",
                }

            if fill["Side"] == trade["Side"]:
                trade["Opening Value"] += value
                trade["Contracts"] += fill["Contracts"]
            else:
                trade["Closing Value"] += value
            trade["Fees"] += fill["Fee"]
            trade["Net Cash"] += (value if fill["Side"] == "Sell" else -value) - fill["Fee"]

            position += signed
            if position == 0:
                trade["Closed"] = fill["Date"]
                trade["Outcome"] = _outcome(trade, fill, stock_trades)
                trades.append(trade)
                trade = None

        if trade is not None:
            trade["Open Contracts"] = abs(position)
            trades.append(trade)

    result = pd.DataFrame(trades)
    if "Open Contracts" not in result.columns:
        result["Open Contracts"] = 0.0
    result["Open Contracts"] = result["Open Contracts"].fillna(0.0)

    # Cash a short put could be forced to spend buying the shares.
    is_short_put = result["Strategy"] == "Short Put"
    result["Collateral"] = (result["Strike"] * result["Contracts"] * OPTION_MULTIPLIER).where(is_short_put)
    return result.sort_values("Opened").reset_index(drop=True)


def value_open_trades(trades: pd.DataFrame, prices: dict[str, float]) -> pd.DataFrame:
    """Mark open trades at current prices. P/L is the cash so far plus what closing now would cost or pay."""
    trades = trades.copy()
    is_open = trades["Outcome"] == "Open"
    trades["Current Price"] = trades["Contract"].map(prices).where(is_open)

    direction = trades["Side"].map({"Sell": -1, "Buy": 1})
    position_value = direction * trades["Open Contracts"] * trades["Current Price"] * OPTION_MULTIPLIER
    trades["P/L"] = trades["Net Cash"].where(~is_open, trades["Net Cash"] + position_value)
    trades["Return on Collateral %"] = trades["P/L"] / trades["Collateral"] * 100
    return trades


def priced_option_trades(fills: pd.DataFrame, stock_trades: pd.DataFrame, fallback_marks: dict[str, float]) -> pd.DataFrame:
    """Build option trades and value open ones at Yahoo's latest price, else moomoo's price at the last sync."""
    from src.pricing import get_option_prices

    trades = build_option_trades(fills, stock_trades)
    if trades.empty:
        return trades

    open_trades = trades[trades["Outcome"] == "Open"]
    symbols = {row["Contract"]: yahoo_option_symbol(row) for _, row in open_trades.iterrows()}
    quotes = get_option_prices(tuple(symbols.values()))
    prices = {
        contract: quotes.get(symbol, fallback_marks.get(contract))
        for contract, symbol in symbols.items()
    }
    return value_open_trades(trades, prices)
