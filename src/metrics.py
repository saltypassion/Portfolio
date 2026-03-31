"""Portfolio analytics helpers for dashboard charts, holdings tables, and lot views."""

from src.pricing import get_latest_prices
import yfinance as yf
import pandas as pd

def calculate_metrics(portfolio):
    """Summarize the current open portfolio into one row per ticker."""
    tickers = [t for t, lots in portfolio.items() if sum(l["units"] for l in lots) > 0]
    prices = get_latest_prices(tickers)

    rows = []
    for ticker in tickers:
        lots = portfolio[ticker]
        shares = sum(lot["units"] for lot in lots)
        cost_basis = sum(lot["units"] * lot["cost_per_unit"] for lot in lots)
        avg_cost = cost_basis / shares

        price = prices.get(ticker, 0.0)
        price = float(price) if price is not None and str(price) != "nan" else 0.0
        equity = shares * price
        unrealised = equity - cost_basis
        unrealised_pct = (unrealised / cost_basis * 100) if cost_basis else 0.0

        rows.append({
            "Ticker": ticker,
            "Shares": shares,
            "Average Cost": round(avg_cost, 2),
            "Cost Basis": round(cost_basis, 2),
            "Current Price": round(price, 2),
            "Equity": round(equity, 2),
            "Unrealised P/L": round(unrealised, 2),
            "Unrealised %": round(unrealised_pct, 2),
        })

    if not rows:
        return pd.DataFrame(columns=["Ticker", "Shares", "Average Cost", "Cost Basis",
                                      "Current Price", "Equity", "Unrealised P/L", "Unrealised %"])
    return pd.DataFrame(rows).sort_values("Equity", ascending=False)

def lot_breakdown(portfolio):
    """Flatten the FIFO portfolio structure into one row per remaining buy lot."""
    rows = []

    for ticker, lots in portfolio.items():
        for lot in lots:
            rows.append({
                "Ticker": ticker,
                "Buy Date": lot["date"],
                "Remaining Shares": lot["units"],
                "Cost Per Share": lot["cost_per_unit"],
                "Total Cost": lot["units"] * lot["cost_per_unit"]
            })

    return pd.DataFrame(rows)

def portfolio_value_and_cost_over_time(df: pd.DataFrame) -> pd.DataFrame:
    """
    Returns a daily time series with:
      - Total Cost (net invested, excludes dividends)
      - Portfolio Value (mark-to-market using daily closes)
    Assumes df columns: Date, Ticker, Type, Units, Price, Fee, Currency (single currency).
    Units are positive; Type is Buy/Sell/Dividend.
    """
    if df.empty:
        return pd.DataFrame(columns=["Total Cost", "Portfolio Value"])

    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date")

    # Only consider Buy/Sell for holdings + cost
    trade_df = df[df["Type"].isin(["Buy", "Sell"])].copy()
    if trade_df.empty:
        return pd.DataFrame(columns=["Total Cost", "Portfolio Value"])

    # Signed units for position tracking
    trade_df["SignedUnits"] = trade_df.apply(
        lambda r: r["Units"] if r["Type"] == "Buy" else -r["Units"],
        axis=1
    )

    # Cashflow for "Total Cost" (net invested):
    # Buy => + (units*price + fee)
    # Sell => - (units*price - fee)  i.e. subtract proceeds, add fee
    trade_df["CashFlow"] = trade_df.apply(
        lambda r: (r["Units"] * r["Price"] + r["Fee"]) if r["Type"] == "Buy"
        else -(r["Units"] * r["Price"] - r["Fee"]),
        axis=1
    )

    # Build daily date index
    start = trade_df["Date"].min().normalize()
    end = df["Date"].max().normalize()
    dates = pd.date_range(start, end, freq="D")

    # Daily net invested (Total Cost)
    daily_cf = trade_df.groupby(trade_df["Date"].dt.normalize())["CashFlow"].sum()
    total_cost = daily_cf.reindex(dates, fill_value=0).cumsum()
    total_cost.name = "Total Cost"

    # Daily positions per ticker
    pos_changes = trade_df.pivot_table(
        index=trade_df["Date"].dt.normalize(),
        columns="Ticker",
        values="SignedUnits",
        aggfunc="sum",
        fill_value=0
    )
    positions = pos_changes.reindex(dates, fill_value=0).cumsum()

    # Download historical closes for all tickers in positions
    tickers = list(positions.columns)
    px = yf.download(tickers, start=start, end=end + pd.Timedelta(days=1), progress=False)

    # Extract Close prices robustly
    if len(tickers) == 1:
        close = px["Close"].to_frame(name=tickers[0])
    else:
        # yfinance often returns multiindex columns: (field, ticker)
        if isinstance(px.columns, pd.MultiIndex):
            close = px["Close"]
        else:
            # fallback (rare)
            close = px[["Close"]]

    # Align to our daily index; forward-fill weekends/holidays
    close = close.reindex(dates).ffill()

    # Portfolio value = sum(shares * close)
    portfolio_value = (positions * close).sum(axis=1)
    portfolio_value.name = "Portfolio Value"

    out = pd.concat([total_cost, portfolio_value], axis=1)
    return out

def portfolio_allocation(portfolio):
    """Compute current market-value allocation by ticker."""
    tickers = list(portfolio.keys())

    if not tickers:
        return pd.DataFrame()

    # Allocation is value-based, so this function refreshes the latest close price.
    prices = yf.download(tickers, period="1d")["Close"]

    if len(tickers) == 1:
        prices = prices.to_frame()

    latest_prices = prices.iloc[-1]

    data = []

    for ticker, lots in portfolio.items():
        shares = sum(lot["units"] for lot in lots)

        if shares == 0:
            continue
        price = latest_prices[ticker]

        value = shares * price

        data.append({
            "Ticker": ticker,
            "Shares": shares,
            "Price": price,
            "Value": value
        })

    df = pd.DataFrame(data)

    df["Allocation %"] = df["Value"] / df["Value"].sum()

    return df

def build_cost_curve(transactions, ticker):
    """Build a cumulative cash-invested curve for a single ticker."""

    tx = transactions[transactions["Ticker"] == ticker].copy()
    tx = tx.sort_values("Date")

    tx["Investment"] = tx.apply(
        lambda row: row["Units"] * row["Price"] if row["Type"] == "Buy"
        else -row["Units"] * row["Price"] if row["Type"] == "Sell"
        else 0,
        axis=1
    )

    tx["Cost Basis"] = tx["Investment"].cumsum()
    tx["Date"] = pd.to_datetime(tx["Date"]).dt.normalize()

    return tx[["Date", "Cost Basis"]]

def build_average_cost_curve(transactions, ticker):
    """Reconstruct average cost after each buy/sell event for a single ticker."""

    tx = transactions[
        (transactions["Ticker"] == ticker) &
        (transactions["Type"].isin(["Buy", "Sell"]))
    ].copy()
    tx = tx.sort_values("Date")
    tx["Date"] = pd.to_datetime(tx["Date"]).dt.normalize()

    total_shares = 0
    total_cost = 0

    rows = []

    for _, row in tx.iterrows():

        if row["Type"] == "Buy":
            # Buys increase both total shares and total cost basis.
            total_shares += row["Units"]
            total_cost += row["Units"] * row["Price"] + row["Fee"]

        elif row["Type"] == "Sell":
            # Sells remove cost basis at the pre-sale average cost, not sale proceeds.
            avg_cost_before_sale = (total_cost / total_shares) if total_shares > 0 else 0
            total_cost -= row["Units"] * avg_cost_before_sale
            total_shares -= row["Units"]
            if total_shares <= 0:
                total_shares = 0
                total_cost = 0

        avg_price = total_cost / total_shares if total_shares > 0 else None

        rows.append({
            "Date": row["Date"],
            "Average Cost": avg_price
        })

    avg_curve = pd.DataFrame(rows)
    if avg_curve.empty:
        return avg_curve

    avg_curve = avg_curve.groupby("Date", as_index=False)["Average Cost"].last()

    return avg_curve
