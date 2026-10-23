"""Pull trades and dividends from a moomoo account through a locally running OpenD.

Read-only: this module never unlocks trading or places orders. Trades come from the
deal (fill) history, and dividends from the account cash flow ledger, which lists each
dividend alongside the withholding tax and fees charged on it.
"""

from __future__ import annotations

import json
import os
import re
import socket
import threading
import time
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

import pandas as pd

from src.config import (
    MOOMOO_CASHFLOW_PATH,
    MOOMOO_SECURITY_FIRM,
    OPTION_COLUMNS,
    MOOMOO_SYNC_LOCK_PATH,
    MOOMOO_SYNC_STATE_PATH,
    OPEND_HOST,
    OPEND_PORT,
    TRANSACTION_COLUMNS,
)

# Deal history can only be queried in windows of up to 360 days.
DEAL_WINDOW_DAYS = 360
# Stop looking further back once this many consecutive windows have no trades.
EMPTY_WINDOWS_BEFORE_STOP = 2

# Cash flows are queried one day at a time, at most 20 requests per 30 seconds.
RATE_LIMIT_CALLS = 20
RATE_LIMIT_SECONDS = 30
# Recent days are re-fetched in case moomoo posts entries late.
CASHFLOW_REFETCH_DAYS = 7
CASHFLOW_SAVE_EVERY_DAYS = 30

FEE_QUERY_BATCH = 50

# A dividend charge posted up to this many days after its payment is folded into that payment.
LATE_CHARGE_DAYS = 7

# Temporary failures (e.g. "Network interruption") are retried after these waits, in seconds.
RETRY_WAITS = (5, 15, 30, 60)

CASHFLOW_COLUMNS = [
    "cashflow_id",
    "clearing_date",
    "settlement_date",
    "currency",
    "cashflow_type",
    "cashflow_direction",
    "cashflow_amount",
    "cashflow_remark",
]

MARKET_SUFFIX = {"US": "", "SG": ".SI", "HK": ".HK"}
MARKET_CURRENCY = {"US": "USD", "SG": "SGD", "HK": "HKD"}
CURRENCY_SUFFIX = {"USD": "", "SGD": ".SI", "HKD": ".HK"}

SIDE_TO_TYPE = {"BUY": "Buy", "BUY_BACK": "Buy", "SELL": "Sell", "SELL_SHORT": "Sell"}

# Dividend remarks come in two formats; moomoo switched from the first to the second in Sep 2026:
#   "NVO 10.00000000 SHARES DIVIDENDS 1.21737596 USD PER SHARE"
#   "GST - NVO DIVIDEND FEE -0.01499999 USD PER SHARE"
#   "MICROSOFT CORP COM(MSFT) dividend, USD 0.91 per share"
#   "NRA withholding tax - MICROSOFT CORP COM(MSFT) dividend, USD 0.91 per share"
REMARK_TICKER_IN_BRACKETS = re.compile(r"\(([A-Z0-9.]+)\) dividend")
REMARK_TICKER_LEADING = re.compile(r"^(?:GST - )?([A-Z0-9.]+)\s")
REMARK_SHARES = re.compile(r"\s([\d.]+) SHARES")
REMARK_PER_SHARE = re.compile(r"(?:DIVIDENDS ([\d.]+) \w+ PER SHARE|dividend, \w+ ([\d.]+) per share)")

# Option contract codes end in YYMMDD + C/P + strike, e.g. "US.PLTR260724P118000".
OPTION_CODE = re.compile(r"\d{6}[CP]\d+$")
OPTION_PARTS = re.compile(r"^(.+?)(\d{6})([CP])(\d+)$")

ProgressCallback = Callable[[float, str], None]


@dataclass
class SyncResult:
    trades: pd.DataFrame
    dividends: pd.DataFrame
    options: pd.DataFrame
    other_cashflow_types: list[str] = field(default_factory=list)
    # Shares moomoo holds that no trade explains (spin-offs, gifts, transfers in), added as $-cost buys.
    received_shares: list[str] = field(default_factory=list)
    # Tickers where moomoo holds fewer shares than the trades add up to (e.g. transferred out).
    position_mismatches: list[str] = field(default_factory=list)


class OpenDNotRunning(RuntimeError):
    pass


class MoomooApiError(RuntimeError):
    pass


def opend_is_running() -> bool:
    try:
        with socket.create_connection((OPEND_HOST, OPEND_PORT), timeout=1):
            return True
    except OSError:
        return False


def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


# Streamlit serves every browser tab from one process, so tabs are told apart by this lock;
# the lock file covers other processes (e.g. a sync run from the command line).
_SYNC_THREAD_LOCK = threading.Lock()


def _read_lock_file() -> dict | None:
    try:
        return json.loads(Path(MOOMOO_SYNC_LOCK_PATH).read_text())
    except (OSError, ValueError):
        return None


def sync_in_progress() -> dict | None:
    """The running sync's progress ({"fraction", "text", "started_at"}), or None if no sync is running."""
    info = _read_lock_file()
    if info and _process_alive(int(info.get("pid", 0))):
        return info
    return None


class _SyncProgress:
    """Reports progress to the caller and to the lock file, so other tabs can show it too."""

    def __init__(self, callback: ProgressCallback | None):
        self.callback = callback
        self.info = {"pid": os.getpid(), "started_at": datetime.now().isoformat(timespec="seconds")}

    def __call__(self, fraction: float, text: str) -> None:
        self.info.update(fraction=round(fraction, 4), text=text)
        Path(MOOMOO_SYNC_LOCK_PATH).write_text(json.dumps(self.info))
        if self.callback:
            self.callback(fraction, text)

    def scaled(self, start: float, end: float) -> ProgressCallback:
        """A callback mapping a step's own 0-1 progress onto [start, end] of the whole sync."""
        return lambda fraction, text: self(start + (end - start) * fraction, text)


@contextmanager
def sync_lock(progress: _SyncProgress):
    """Allow one sync at a time: moomoo's rate limit is shared across everything using the account."""
    busy = MoomooApiError("Another moomoo sync is already running. Wait for it to finish, then try again.")
    if sync_in_progress() or not _SYNC_THREAD_LOCK.acquire(blocking=False):
        raise busy

    try:
        progress(0.0, "Starting sync...")
        yield
    finally:
        Path(MOOMOO_SYNC_LOCK_PATH).unlink(missing_ok=True)
        _SYNC_THREAD_LOCK.release()


def load_sync_state() -> dict:
    path = Path(MOOMOO_SYNC_STATE_PATH)
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _save_sync_state(state: dict) -> None:
    Path(MOOMOO_SYNC_STATE_PATH).write_text(json.dumps(state, indent=2))


def _load_cashflow_cache() -> pd.DataFrame:
    path = Path(MOOMOO_CASHFLOW_PATH)
    if not path.exists():
        return pd.DataFrame(columns=CASHFLOW_COLUMNS)
    return pd.read_csv(path, dtype={"clearing_date": str, "cashflow_remark": str}, keep_default_na=False)


def _save_cashflow_cache(df: pd.DataFrame) -> None:
    df.sort_values(["clearing_date", "cashflow_id"]).to_csv(MOOMOO_CASHFLOW_PATH, index=False)


def to_app_ticker(code: str) -> str:
    """Convert moomoo codes ("US.AAPL", "HK.00700") to the Yahoo-style tickers the app uses."""
    market, _, symbol = code.partition(".")
    if market == "HK":
        symbol = symbol.lstrip("0").zfill(4)
    return symbol + MARKET_SUFFIX.get(market, "")


class _RateLimiter:
    def __init__(self, calls: int, seconds: float):
        self.calls = calls
        self.seconds = seconds
        self.history: deque[float] = deque()

    def wait(self) -> None:
        now = time.monotonic()
        while self.history and now - self.history[0] >= self.seconds:
            self.history.popleft()
        if len(self.history) >= self.calls:
            time.sleep(self.seconds - (now - self.history[0]) + 0.1)
        self.history.append(time.monotonic())


class MoomooClient:
    """Thin read-only wrapper around the moomoo SDK trade context."""

    def __init__(self):
        if not opend_is_running():
            raise OpenDNotRunning(
                f"moomoo OpenD is not running on {OPEND_HOST}:{OPEND_PORT}. Open OpenD and log in, then try again."
            )

        # Imported lazily so the rest of the app works without the SDK installed.
        from moomoo import RET_OK, OpenSecTradeContext, SecurityFirm, TrdEnv, TrdMarket

        self._ret_ok = RET_OK
        self._trd_env = TrdEnv.REAL
        self._ctx = OpenSecTradeContext(
            filter_trdmarket=TrdMarket.US,
            host=OPEND_HOST,
            port=OPEND_PORT,
            security_firm=getattr(SecurityFirm, MOOMOO_SECURITY_FIRM),
        )
        self._limiter = _RateLimiter(RATE_LIMIT_CALLS, RATE_LIMIT_SECONDS)
        self.acc_id = self._find_account()

    def close(self) -> None:
        self._ctx.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _call(self, method: str, **kwargs) -> pd.DataFrame:
        for wait in (*RETRY_WAITS, None):
            ret, data = getattr(self._ctx, method)(**kwargs)
            if ret == self._ret_ok:
                return data
            if wait is None:
                raise MoomooApiError(f"{method} failed: {data}")
            time.sleep(wait)

    def _find_account(self) -> int:
        accounts = self._call("get_acc_list")
        real = accounts[accounts["trd_env"] == self._trd_env]
        if real.empty:
            raise MoomooApiError("OpenD is logged in, but no real (non-paper) account was found.")
        return int(real["acc_id"].iloc[0])

    def deals(self, start: date, end: date) -> pd.DataFrame:
        return self._call(
            "history_deal_list_query",
            start=f"{start:%Y-%m-%d} 00:00:00",
            end=f"{end:%Y-%m-%d} 23:59:59",
            trd_env=self._trd_env,
            acc_id=self.acc_id,
        )

    def order_fees(self, order_ids: list[str]) -> pd.DataFrame:
        return self._call("order_fee_query", order_id_list=order_ids, trd_env=self._trd_env, acc_id=self.acc_id)

    def cashflows(self, day: date) -> pd.DataFrame:
        self._limiter.wait()
        return self._call(
            "get_acc_cash_flow",
            clearing_date=f"{day:%Y-%m-%d}",
            trd_env=self._trd_env,
            acc_id=self.acc_id,
        )

    def positions(self) -> pd.DataFrame:
        return self._call("position_list_query", trd_env=self._trd_env, acc_id=self.acc_id, refresh_cache=True)


def fetch_trades(client: MoomooClient, today: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fetch every fill on the account, walking back in 360-day windows.

    Returns (stock/ETF trades as app transactions, option fills in the options schema).
    """
    frames = []
    empty_windows = 0
    end = today
    while empty_windows < EMPTY_WINDOWS_BEFORE_STOP:
        start = end - timedelta(days=DEAL_WINDOW_DAYS - 1)
        window = client.deals(start, end)
        if window.empty:
            empty_windows += 1
        else:
            empty_windows = 0
            frames.append(window)
        end = start - timedelta(days=1)

    if not frames:
        return pd.DataFrame(columns=TRANSACTION_COLUMNS), pd.DataFrame(columns=OPTION_COLUMNS)

    deals = pd.concat(frames, ignore_index=True).drop_duplicates("deal_id")
    deals = deals[deals["status"] == "OK"].copy()
    deals["Date"] = pd.to_datetime(deals["create_time"]).dt.floor("s")
    deals = deals.sort_values(["Date", "deal_id"])

    # Fees are charged per order; put them on the order's first fill, as moomoo's export does.
    order_ids = deals["order_id"].unique().tolist()
    fee_frames = [
        client.order_fees(order_ids[i:i + FEE_QUERY_BATCH])
        for i in range(0, len(order_ids), FEE_QUERY_BATCH)
    ]
    fees = pd.concat(fee_frames, ignore_index=True).set_index("order_id")["fee_amount"]
    is_first_fill = ~deals.duplicated("order_id")
    deals["Fee"] = deals["order_id"].map(fees).fillna(0.0).where(is_first_fill, 0.0).round(2)
    deals["Side"] = deals["trd_side"].map(SIDE_TO_TYPE)
    deals["Currency"] = deals["code"].str.partition(".")[0].map(MARKET_CURRENCY).fillna("USD")
    deals = deals.dropna(subset=["Side"])

    is_option = deals["code"].str.contains(OPTION_CODE)
    return _stock_trades(deals[~is_option]), _option_fills(deals[is_option])


def _stock_trades(deals: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "Date": deals["Date"],
        "Ticker": deals["code"].map(to_app_ticker),
        "Type": deals["Side"],
        "Units": deals["qty"].astype(float),
        "Price": deals["price"].astype(float),
        "Fee": deals["Fee"].astype(float),
        "Currency": deals["Currency"],
    }, columns=TRANSACTION_COLUMNS).reset_index(drop=True)


def parse_option_code(code: str) -> dict:
    """Split "US.PLTR260724P118000" into underlying, expiry, right and strike."""
    market, _, contract = code.partition(".")
    match = OPTION_PARTS.match(contract)
    underlying, expiry, right, strike = match.groups()
    return {
        "Contract": contract,
        "Underlying": underlying + MARKET_SUFFIX.get(market, ""),
        "Expiry": pd.to_datetime(expiry, format="%y%m%d"),
        "Right": "Put" if right == "P" else "Call",
        "Strike": int(strike) / 1000,
    }


def _option_fills(deals: pd.DataFrame) -> pd.DataFrame:
    if deals.empty:
        return pd.DataFrame(columns=OPTION_COLUMNS)

    parts = pd.DataFrame([parse_option_code(code) for code in deals["code"]], index=deals.index)
    fills = pd.concat([deals[["Date", "Side", "Fee", "Currency"]], parts], axis=1)
    fills["Contracts"] = deals["qty"].astype(float)
    fills["Price"] = deals["price"].astype(float)
    return fills[OPTION_COLUMNS].reset_index(drop=True)


def option_marks(positions: pd.DataFrame) -> dict[str, float]:
    """moomoo's latest price per open option contract, as a fallback when Yahoo has no quote."""
    if positions.empty:
        return {}
    options = positions[positions["code"].str.contains(OPTION_CODE)]
    return {
        code.partition(".")[2]: float(price)
        for code, price in zip(options["code"], options["nominal_price"])
    }


def update_cashflow_cache(
    client: MoomooClient,
    first_day: date,
    today: date,
    progress: ProgressCallback | None = None,
) -> pd.DataFrame:
    """Fetch cash flows for days not cached yet (plus a few recent days) and return the full cache."""
    state = load_sync_state()
    cache = _load_cashflow_cache()

    fetched_through = state.get("cashflows_fetched_through")
    resume_from = first_day
    if fetched_through:
        resume_from = max(first_day, date.fromisoformat(fetched_through) - timedelta(days=CASHFLOW_REFETCH_DAYS))

    days = pd.date_range(resume_from, today).date.tolist()
    new_frames = []

    def flush(through: date) -> None:
        nonlocal cache, new_frames
        fetched = [frame[CASHFLOW_COLUMNS] for frame in new_frames if not frame.empty]
        refetched = cache["clearing_date"].astype(str) >= f"{resume_from:%Y-%m-%d}"
        refetched &= cache["clearing_date"].astype(str) <= f"{through:%Y-%m-%d}"
        cache = pd.concat([cache[~refetched], *fetched], ignore_index=True)
        _save_cashflow_cache(cache)
        state["cashflows_fetched_through"] = f"{through:%Y-%m-%d}"
        _save_sync_state(state)

    for i, day in enumerate(days, start=1):
        new_frames.append(client.cashflows(day))
        if progress:
            text = f"Reading dividends and cash flows: {day:%d %b %Y} ({i}/{len(days)} days)"
            seconds_left = (len(days) - i) * RATE_LIMIT_SECONDS / RATE_LIMIT_CALLS
            if seconds_left >= 60:
                text += f", about {seconds_left / 60:.0f} min left"
            progress(i / len(days), text)
        if i % CASHFLOW_SAVE_EVERY_DAYS == 0 or i == len(days):
            flush(day)

    return cache


def _is_dividend_cashflow(cashflows: pd.DataFrame) -> pd.Series:
    flow_type = cashflows["cashflow_type"].astype(str)
    remark = cashflows["cashflow_remark"].astype(str)
    return (
        flow_type.str.contains("Dividend")
        | flow_type.str.contains("Withholding")
        | ((flow_type == "GST") & remark.str.contains("DIVIDEND"))
    )


def build_dividends(cashflows: pd.DataFrame) -> pd.DataFrame:
    """Combine each dividend with its withholding tax, ADR fee and GST into one app transaction."""
    if cashflows.empty:
        return pd.DataFrame(columns=TRANSACTION_COLUMNS)

    flows = cashflows[_is_dividend_cashflow(cashflows)].copy()
    if flows.empty:
        return pd.DataFrame(columns=TRANSACTION_COLUMNS)

    remark = flows["cashflow_remark"].astype(str)
    flows["amount"] = pd.to_numeric(flows["cashflow_amount"], errors="coerce").fillna(0.0)
    flows["is_payment"] = flows["cashflow_type"] == "Cash Dividend"
    flows["symbol"] = remark.str.extract(REMARK_TICKER_IN_BRACKETS, expand=False).fillna(
        remark.str.extract(REMARK_TICKER_LEADING, expand=False)
    )
    flows["shares"] = pd.to_numeric(remark.str.extract(REMARK_SHARES, expand=False), errors="coerce")
    per_share = remark.str.extract(REMARK_PER_SHARE).bfill(axis=1).iloc[:, 0]
    flows["per_share"] = pd.to_numeric(per_share, errors="coerce")
    flows = flows.dropna(subset=["symbol"])

    # The newer format gives no share count, so derive it from the amount and the per-share rate.
    derived_shares = (flows["amount"] / flows["per_share"]).round()
    flows["shares"] = flows["shares"].fillna(derived_shares.where(derived_shares > 0))

    flows["gross"] = flows["amount"].where(flows["is_payment"], 0.0)
    flows["charges"] = (-flows["amount"]).where(~flows["is_payment"], 0.0)
    flows["payment_shares"] = flows["shares"].where(flows["is_payment"])

    grouped = (
        flows.groupby(["clearing_date", "symbol", "currency"], as_index=False)
        .agg(gross=("gross", "sum"), charges=("charges", "sum"), shares=("payment_shares", "max"))
    )

    # Charges sometimes post a few days after their payment (e.g. GST on an ADR fee). Fold each one
    # into the same ticker's latest payment; one with no payment still moves cash, so it is kept.
    grouped["clearing_date"] = pd.to_datetime(grouped["clearing_date"])
    grouped = grouped.sort_values("clearing_date").reset_index(drop=True)
    orphans = grouped.index[grouped["gross"] == 0]
    for i in orphans:
        row = grouped.loc[i]
        earlier = grouped[
            (grouped["symbol"] == row["symbol"])
            & (grouped["gross"] > 0)
            & (grouped["clearing_date"] <= row["clearing_date"])
            & (grouped["clearing_date"] >= row["clearing_date"] - pd.Timedelta(days=LATE_CHARGE_DAYS))
        ]
        if not earlier.empty:
            grouped.loc[earlier.index[-1], "charges"] += row["charges"]
            grouped = grouped.drop(i)

    has_shares = grouped["shares"].fillna(0) > 0
    units = grouped["shares"].where(has_shares, 0.0)
    price = (grouped["gross"] / grouped["shares"]).where(has_shares, 0.0)

    dividends = pd.DataFrame({
        "Date": grouped["clearing_date"],
        "Ticker": grouped["symbol"] + grouped["currency"].map(CURRENCY_SUFFIX).fillna(""),
        "Type": "Dividend",
        "Units": units,
        "Price": price.round(8),
        "Fee": grouped["charges"].round(2),
        "Currency": grouped["currency"],
    })
    return dividends.sort_values(["Date", "Ticker"]).reset_index(drop=True)


def other_cashflow_types(cashflows: pd.DataFrame) -> list[str]:
    """Cash flow types the sync does not turn into transactions, for display."""
    if cashflows.empty:
        return []
    ignored = cashflows.loc[~_is_dividend_cashflow(cashflows), "cashflow_type"].astype(str)
    return sorted(set(ignored))


def reconcile_positions(
    trades: pd.DataFrame,
    dividends: pd.DataFrame,
    positions: pd.DataFrame,
    state: dict,
    today: date,
) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Add buys for shares moomoo holds that the trade history doesn't explain.

    Spin-offs, gifted shares and transfers in never appear as trades. Each shortfall becomes a
    buy at moomoo's average cost ($0 for spin-offs). Returns (extra buys, descriptions, mismatches).
    """
    if positions.empty:
        return pd.DataFrame(columns=TRANSACTION_COLUMNS), [], []

    stocks = positions[~positions["code"].str.contains(OPTION_CODE) & (positions["qty"] > 0)].copy()
    stocks["Ticker"] = stocks["code"].map(to_app_ticker)

    signed = trades["Units"].where(trades["Type"] == "Buy", -trades["Units"])
    traded_shares = signed.groupby(trades["Ticker"]).sum()

    first_seen = state.setdefault("received_shares_first_seen", {})
    rows, received, mismatches = [], [], []

    for _, position in stocks.iterrows():
        ticker = position["Ticker"]
        shortfall = float(position["qty"]) - float(traded_shares.get(ticker, 0.0))
        if shortfall < 0:
            mismatches.append(f"{ticker} (moomoo {position['qty']:g}, trades {traded_shares.get(ticker, 0.0):g})")
            continue
        if shortfall == 0:
            continue

        # Date it at the first dividend if the stock was never traded (it must have been held by then);
        # otherwise at the first sync that noticed it, remembered so the date stays put.
        first_seen.setdefault(ticker, f"{today:%Y-%m-%d}")
        received_on = pd.Timestamp(first_seen[ticker])
        ticker_dividends = dividends.loc[dividends["Ticker"] == ticker, "Date"]
        if ticker not in traded_shares.index and not ticker_dividends.empty:
            received_on = min(received_on, ticker_dividends.min())

        price = max(float(position["average_cost"]), 0.0)
        market = position["code"].partition(".")[0]
        rows.append({
            "Date": received_on,
            "Ticker": ticker,
            "Type": "Buy",
            "Units": shortfall,
            "Price": price,
            "Fee": 0.0,
            "Currency": MARKET_CURRENCY.get(market, "USD"),
        })
        received.append(f"{shortfall:g} {ticker} at ${price:,.2f}")

    return pd.DataFrame(rows, columns=TRANSACTION_COLUMNS), received, mismatches


def sync_account(progress: ProgressCallback | None = None) -> SyncResult:
    """Fetch the account's full trade, option and dividend history."""
    today = date.today()
    report = _SyncProgress(progress)
    with sync_lock(report):
        report(0.02, "Connecting to OpenD...")
        with MoomooClient() as client:
            report(0.05, "Reading trade history...")
            trades, options = fetch_trades(client, today)
            report(0.20, f"Found {len(trades)} stock trades and {len(options)} option trades")

            if trades.empty and options.empty:
                return SyncResult(trades, pd.DataFrame(columns=TRANSACTION_COLUMNS), options)

            # No dividends can be earned before the first trade.
            first_day = pd.concat([trades["Date"], options["Date"]]).min().date()
            cashflows = update_cashflow_cache(client, first_day, today, report.scaled(0.20, 0.85))

            report(0.88, "Checking your holdings against moomoo...")
            positions = client.positions()

        report(0.94, "Matching dividends with their tax and fees...")
        dividends = build_dividends(cashflows)
        state = load_sync_state()
        received_buys, received, mismatches = reconcile_positions(trades, dividends, positions, state, today)
        if not received_buys.empty:
            trades = pd.concat([trades, received_buys], ignore_index=True).sort_values("Date").reset_index(drop=True)

        state["option_marks"] = option_marks(positions)
        state["last_synced_at"] = datetime.now().isoformat(timespec="seconds")
        _save_sync_state(state)

    return SyncResult(
        trades=trades,
        dividends=dividends,
        options=options,
        other_cashflow_types=other_cashflow_types(cashflows),
        received_shares=received,
        position_mismatches=mismatches,
    )
