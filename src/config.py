"""Central file-system paths and column schemas used by the app."""

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PERSONAL_DATA_DIR = os.path.join(BASE_DIR, "data")
DEMO_DATA_DIR = os.path.join(BASE_DIR, "demo_data")

# A fresh clone has no personal data/ folder (it is git-ignored), so the app runs on the
# bundled demo data instead. Creating data/ switches to your own data.
DEMO_MODE = not os.path.isdir(PERSONAL_DATA_DIR) and os.path.isdir(DEMO_DATA_DIR)
DATA_DIR = DEMO_DATA_DIR if DEMO_MODE else PERSONAL_DATA_DIR
TRADE_PATH = os.path.join(DATA_DIR, "trades.csv")
DIVIDEND_PATH = os.path.join(DATA_DIR, "dividends.csv")
WATCHLIST_PATH = os.path.join(DATA_DIR, "watchlist.csv")
DATA_PATH = os.path.join(DATA_DIR, "transactions.csv")
OPTIONS_PATH = os.path.join(DATA_DIR, "options.csv")

# Raw moomoo cash flows are cached so each sync only fetches days not seen yet.
MOOMOO_CASHFLOW_PATH = os.path.join(DATA_DIR, "moomoo_cashflows.csv")
MOOMOO_SYNC_STATE_PATH = os.path.join(DATA_DIR, "moomoo_sync.json")
MOOMOO_SYNC_LOCK_PATH = os.path.join(DATA_DIR, "moomoo_sync.lock")

# moomoo OpenD gateway, running locally while syncing.
OPEND_HOST = "127.0.0.1"
OPEND_PORT = 11111
MOOMOO_SECURITY_FIRM = "FUTUSG"

TRANSACTION_COLUMNS = [
    "Date",
    "Ticker",
    "Type",
    "Units",
    "Price",
    "Fee",
    "Currency",
]

# One row per option fill. Prices are per share; one contract covers OPTION_MULTIPLIER shares.
OPTION_COLUMNS = [
    "Date",
    "Contract",
    "Underlying",
    "Expiry",
    "Right",
    "Strike",
    "Side",
    "Contracts",
    "Price",
    "Fee",
    "Currency",
]
OPTION_MULTIPLIER = 100

WATCHLIST_COLUMNS = [
    "Date Added",
    "Ticker",
    "Watch Type",
    "Target Price",
    "Fair Value",
    "Priority",
    "Status",
    "Notes",
]
