"""Central file-system paths and column schemas used by the app."""

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
RAW_UPLOAD_DIR = os.path.join(DATA_DIR, "uploaded")
TRADE_PATH = os.path.join(DATA_DIR, "trades.csv")
DIVIDEND_PATH = os.path.join(DATA_DIR, "dividends.csv")
WATCHLIST_PATH = os.path.join(DATA_DIR, "watchlist.csv")
DATA_PATH = os.path.join(DATA_DIR, "transactions.csv")

TRANSACTION_COLUMNS = [
    "Date",
    "Ticker",
    "Type",
    "Units",
    "Price",
    "Fee",
    "Currency",
]

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
