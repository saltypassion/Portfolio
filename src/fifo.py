"""FIFO portfolio engine used to derive open lots, realised gains, and dividends."""

from collections import defaultdict

def run_fifo(df):
    portfolio = defaultdict(list)
    realised = defaultdict(float)
    dividends = defaultdict(float)

    for _, row in df.iterrows():
        ticker = row["Ticker"]
        txn_type = row["Type"]
        units = row["Units"]
        total_cost = row["TotalCost"]

        # Each buy becomes a new lot that can later be consumed in FIFO order.
        if txn_type == "Buy":
            portfolio[ticker].append({
                "date": row["Date"],
                "units": units,
                "cost_per_unit": total_cost / units
            })

        # Sells consume the oldest remaining lots first.
        elif txn_type == "Sell":
            units_to_sell = units
            proceeds = total_cost
            cost_basis = 0

            while units_to_sell > 0:
                lot = portfolio[ticker][0]
                available = lot["units"]

                used = min(available, units_to_sell)
                cost_basis += used * lot["cost_per_unit"]

                lot["units"] -= used
                units_to_sell -= used

                if lot["units"] == 0:
                    portfolio[ticker].pop(0)

            realised[ticker] += proceeds - cost_basis

        # Dividends do not affect open lots, only cash received by ticker.
        elif txn_type == "Dividend":
            dividends[ticker] += total_cost

    return portfolio, realised, dividends
