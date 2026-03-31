# Portfolio Tracker

A Streamlit portfolio tracker for importing Moomoo trades, logging manual dividends, managing buy/sell watchlists, and analyzing holdings with stock detail, lot breakdown, and allocation views.

## Overview

This project is a local portfolio dashboard built around CSV-based storage. It is designed for a workflow where:

- trade history is imported from Moomoo
- dividends can be added manually when the broker export does not include them
- watchlist ideas can be tracked separately from existing holdings
- portfolio analytics are calculated from the combined transaction history

The app uses Streamlit for the interface, pandas for data handling, Plotly for charts, and `yfinance` for market data and ticker metadata.

## Features

- Import Moomoo trade exports and deduplicate repeated imports
- Store trades, dividends, and watchlist items in separate CSV source files
- Rebuild a combined transactions file automatically
- Track manual dividend entries
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

- `Import Moomoo Data`
  Upload, preview, clean, and import broker exports.

- `Add Dividends`
  Add dividend payments manually when they are missing from the broker CSV.

- `Manage Data`
  Review recent source rows and remove the last imported trade or dividend row if needed.

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
│       ├── 5_Import_Moomoo_Data.py
│       ├── 6_Add_Dividends.py
│       └── 7_Manage_Data.py
├── data/
│   ├── trades.csv
│   ├── dividends.csv
│   ├── watchlist.csv
│   ├── transactions.csv
│   └── uploaded/
└── src/
    ├── config.py
    ├── fifo.py
    ├── io.py
    ├── metrics.py
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

### Moomoo import flow

1. Upload a Moomoo CSV on the import page.
2. The file is transformed into the app schema.
3. Existing imported trades are checked to avoid duplicates.
4. Net-new rows are appended to `data/trades.csv`.
5. The combined `data/transactions.csv` file is rebuilt automatically.

### Dividend flow

1. Add dividend payments manually on the Add Dividends page.
2. Entries are stored in `data/dividends.csv`.
3. The combined `data/transactions.csv` file is rebuilt automatically.

### Watchlist flow

1. Add a buy or sell watchlist item.
2. The app stores the row in `data/watchlist.csv`.
3. Live prices are compared against the target price.
4. Status is derived automatically as `Watching`, `Ready`, or `No Price`.

## Running the App

From the project root:

```bash
streamlit run app/Dashboard.py
```

If `streamlit` is not on your PATH:

```bash
python3 -m streamlit run app/Dashboard.py
```

## Suggested Environment Setup

Create and activate a virtual environment, then install the core dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install streamlit pandas plotly yfinance streamlit-autorefresh
```

If you already manage dependencies another way, use that instead.

## Notes

- This app is built for local use and stores data as CSV files.
- Market data and company/fund metadata are pulled from Yahoo Finance through `yfinance`.
- ETF metadata may differ from equities, so the app uses `Fund Category` and `Fund Family` where appropriate.
- Re-importing Moomoo exports is expected as part of the normal monthly workflow.

## Future Improvements

- Add editable table-style watchlist management
- Add stronger validation and import diagnostics
- Add tests around FIFO, imports, and derived metrics
- Add better ETF exposure analysis
- Add export or backup tools
