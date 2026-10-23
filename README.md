# Portfolio Tracker

A Streamlit portfolio tracker that syncs trades, options and dividends from a moomoo brokerage account, tracks option income, manages buy/sell watchlists, and analyzes holdings with stock detail, FIFO lot breakdown, and allocation views.

**Try it without an account:** clone the repo and run it. With no personal `data/` folder, the app starts in demo mode on a sample portfolio (see [Quick Start](#quick-start)).

## Overview

This project is a local portfolio dashboard built around CSV-based storage. It is designed for a workflow where:

- trade, option and dividend history is synced from moomoo through the OpenD gateway
- watchlist ideas can be tracked separately from existing holdings
- portfolio analytics are calculated from the combined transaction history

The app uses Streamlit for the interface, pandas for data handling, Plotly for charts, and `yfinance` for market data and ticker metadata.

## Features

- Sync trades, options and dividends (with exact withholding tax and ADR fees) from moomoo, read-only
- Track option strategies: realised income, live P/L on open positions, win rate, and return on collateral
- Store trades, dividends, and watchlist items in separate CSV source files
- Rebuild a combined transactions file automatically
- View current holdings, unrealised P/L, and lifetime dividends
- Inspect individual stocks on a dedicated Stock Details page
- Track buy and sell watchlists with target prices and optional fair values
- Analyze remaining FIFO lots in the Lot Breakdown page
- View portfolio allocation by ticker, type, sector/fund category, and industry/fund family

## App Pages

- `Dashboard`
  Main portfolio overview with holdings, watchlist snapshot, performance metrics, and allocation charts.

- `Stock Details`
  Single-ticker page for price history, watchlist context, transactions, and dividends.

- `Dividends`
  Dividend totals, by-stock breakdown, monthly income, and cumulative dividend growth.

- `Lot Breakdown`
  Open FIFO lots, age of lots, cost basis, and unrealised P/L by ticker and by lot.

- `Watchlist`
  Separate buy and sell watchlists with target prices, fair value, priority, notes, and quick navigation to Stock Details.

- `Options`
  Realised option income, open positions valued live, win rate, return on collateral, and every closed trade.

- `Sync Moomoo`
  Pull the full trade, option and dividend history from moomoo. Needs OpenD running while syncing.

## Project Structure

```text
Portfolio/
├── app/
│   ├── Dashboard.py
│   └── pages/
│       ├── 1_Stock_Details.py
│       ├── 2_Dividends.py
│       ├── 3_Lot_Breakdown.py
│       ├── 4_Watchlist.py
│       ├── 5_Options.py
│       └── 6_Sync_Moomoo.py
├── demo_data/            # sample portfolio used in demo mode (tracked)
├── scripts/
│   ├── make_demo_data.py # regenerates demo_data/ from real historical prices
│   └── moomoo_probe.py   # read-only check of the moomoo cash flow API
├── data/                 # your personal data (git-ignored)
│   ├── trades.csv
│   ├── dividends.csv
│   ├── watchlist.csv
│   ├── transactions.csv
│   ├── options.csv
│   ├── moomoo_cashflows.csv
│   └── moomoo_sync.json
└── src/
    ├── config.py
    ├── fifo.py
    ├── io.py
    ├── metrics.py
    ├── options.py
    ├── pricing.py
    ├── ui.py
    └── importers/
        └── moomoo.py
```

## Data Model

### Trades and Dividends

The app stores portfolio activity using these transaction columns:

- `Date`
- `Ticker`
- `Type`
- `Units`
- `Price`
- `Fee`
- `Currency`

### Watchlist

Watchlist entries use:

- `Date Added`
- `Ticker`
- `Watch Type`
- `Target Price`
- `Fair Value`
- `Priority`
- `Status`
- `Notes`

## How Data Flows

### moomoo sync flow

1. Open moomoo OpenD and log in (it only needs to run while syncing).
2. Click `Sync now` on the Sync Moomoo page.
3. All fills are read from the deal history, with each order's fees on its first fill. Stock/ETF fills go to `data/trades.csv`; option fills go to `data/options.csv`, kept apart so they don't distort holdings.
4. Shares moomoo holds that no trade explains (spin-offs, gifts, transfers in) are added as buys at moomoo's average cost.
5. Dividends are read from the account cash flow ledger. Each dividend is combined with its withholding tax, ADR fee and GST, which are stored as the dividend's `Fee`.
6. `data/trades.csv`, `data/dividends.csv` and `data/options.csv` are replaced with the synced data, and `data/transactions.csv` is rebuilt.

### Options

Option fills are grouped into trades per contract, from opening until the position is flat again. Each trade gets a strategy (`Short Put`, `Long Call`, ...) and an outcome: `Bought back` / `Sold`, `Expired` (moomoo closes these with a $0 fill), or `Assigned` / `Exercised` when shares change hands at the strike around expiry. P/L uses the x100 multiplier and includes all fees. Multi-leg strategies such as spreads show as their separate legs.

Cash flows can only be read one day at a time (20 requests per 30 seconds), so the first sync takes about 25 minutes. Raw cash flows are cached in `data/moomoo_cashflows.csv`, so later syncs only read new days. The OpenD address and moomoo region (`FUTUSG`) are set in `src/config.py`.

The sync is read-only: it never unlocks trading or places orders.

### Watchlist flow

1. Add a buy or sell watchlist item.
2. The app stores the row in `data/watchlist.csv`.
3. Live prices are compared against the target price.
4. Status is derived automatically as `Watching`, `Ready`, or `No Price`.

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m streamlit run app/Dashboard.py
```

### Demo mode

A fresh clone has no `data/` folder, so the app runs on the sample portfolio in `demo_data/`: made-up trades priced at real historical closes, dividends from real dividend history, and short puts covering every outcome (expired, bought back at a profit and at a loss, assigned, and one still open). A banner marks every page as demo data, and syncing is disabled so the samples aren't overwritten.

To refresh the samples against current prices: `python3 scripts/make_demo_data.py`.

### Using your own moomoo account

1. Create a `data/` folder in the project root. This switches the app out of demo mode. The folder is git-ignored, so your data is never committed.
2. Install [moomoo OpenD](https://openapi.moomoo.com/), open it and log in.
3. Set your moomoo region in `src/config.py` (`MOOMOO_SECURITY_FIRM`, e.g. `FUTUSG` for moomoo Singapore).
4. Start the app, open **Sync Moomoo** and click **Sync now**.

## Notes

- This app is built for local use and stores data as CSV files. Personal data lives in the git-ignored `data/` folder.
- Market data and company/fund metadata are pulled from Yahoo Finance through `yfinance`.
- ETF metadata may differ from equities, so the app uses `Fund Category` and `Fund Family` where appropriate.
- moomoo is the source of truth for trades, options and dividends: each sync overwrites `trades.csv`, `dividends.csv` and `options.csv`.

## Future Improvements

- Add editable table-style watchlist management
- Add stronger validation and import diagnostics
- Add tests around FIFO, the moomoo sync, and derived metrics
- Group multi-leg option strategies (spreads, rolls) into one trade
- Add better ETF exposure analysis
- Add export or backup tools
